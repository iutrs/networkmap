#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import re
import os
import sys
import time
import socket

import logging
import argparse
import ConfigParser

from multiprocessing import Process, Manager, Queue

import paramiko

from NetworkOutputParser import *

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 1024
DEFAULT_MAX_ATTEMPTS = 1
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = None

config = ConfigParser.RawConfigParser()


class NetworkExplorer(object):
    def __init__(self, device):

        self.device = device
        self.hostname = device.system_name

        self.network_parser = None

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.shell = None

        self.ignore_list = ()

        self.ssh_timeout = DEFAULT_TIMEOUT
        self.ssh_max_bytes = DEFAULT_MAX_BYTES
        self.ssh_max_attempts = DEFAULT_MAX_ATTEMPTS
        self.attempts_count = 0

        self.ssh_username = DEFAULT_USERNAME
        self.ssh_password = DEFAULT_PASSWORD
        self.ssh_private_key = None

        try:
            self.ignore_list = config.get('DEFAULT', 'Ignore').split()

            self.ssh_timeout = config.getfloat('SSH', 'Timeout')
            self.ssh_max_bytes = config.getint('SSH', 'MaximumBytesToReceive')
            self.ssh_max_attempts = config.getint('SSH', 'MaximumAttempts')

            self.ssh_username = config.get('SSH', 'Username')
            self.ssh_password = config.get('SSH', 'Password')
            self.ssh_private_key = paramiko.RSAKey.from_private_key_file(
                config.get('SSH', 'PathToPrivateKey'))

        except ConfigParser.Error as cpe:
            logging.error("Configuration error: %s", cpe)
        except Exception as e:
            logging.error("Unexpected error: %s", e)

    def explore_lldp(self, explored_devices, queue):
        """
        Explores a device using the LLDP protocol in order to add its valid \
        neighbors in the queue.
        :param explored_devices: The dict of the devices already explored
        :type explored_devices: {str : Device}
        :param queue: The queue of the next devices to explore
        :type queue: Queue()
        """

        if not self._open_ssh_connection():
            return

        time.sleep(1)

        # Determining the type of the current device from the switch prompt
        switch_prompt = self._receive_ssh_output()

        self.network_parser = NetworkOutputParser.get_parser_type(switch_prompt)

        if self.network_parser is None:
            logging.warning("Could not recognize device %s. Here is the \
                switch prompt: %s", self.hostname, switch_prompt)
            return

        # Sending preparation commands to switch
        self._prepare_switch()

        # Building current device's informations if missing
        if self.device is None or self.device.mac_address is None:
            self.device = self._build_current_device()

        if self.device is None or self.device.mac_address is None:
            logging.warning("Could not parse device %s.", self.hostname)
            return

        logging.info("Discovering lldp neighbors for %s...", self.hostname)

        neighbors = self._get_lldp_neighbors(self.device)

        self._close_ssh_connection()

        explored_devices[self.device.mac_address] = self.device

        for neighbor in neighbors:
            valid = neighbor.is_valid_lldp_device()
            explored = neighbor.mac_address in explored_devices

            if valid and not explored:
                explored_devices[neighbor.mac_address] = neighbor

                if not self._ignore(neighbor.ip_address) and \
                   not self._ignore(neighbor.system_name):
                    queue.put(neighbor)

    def _build_current_device(self):
        info = self._show_lldp_local_device()
        return self.network_parser.parse_device_from_lldp_local_info(info)

    def _get_lldp_neighbors(self, device):

        neighbors_result = self._show_lldp_neighbors()

        if isinstance(self.network_parser, LinuxNetworkOutputParser):
            vms = self._show_virtual_machines()
            device.virtual_machines = self.network_parser.parse_vms_list(vms)
            neighbors = self.network_parser\
                .parse_devices_from_lldp_remote_info(device, neighbors_result)
            return neighbors

        if isinstance(self.network_parser,
                      (HPNetworkOutputParser, JuniperNetworkOutputParser)):

            device.interfaces = self._get_lldp_interfaces(neighbors_result)
            self._assign_vlans_to_interfaces(device.interfaces)

            neighbors_result = ""

            for interface in device.interfaces:
                if interface.is_valid_lldp_interface():

                    partial_result = self._show_lldp_neighbor_detail(
                        interface.local_port)
                    if partial_result is not None:
                        neighbors_result += partial_result

            return self.network_parser\
                .parse_devices_from_lldp_remote_info(neighbors_result)

    def _get_lldp_interfaces(self, lldp_result):
        interfaces = self.network_parser\
            .parse_interfaces_from_lldp_remote_info(lldp_result)
        return interfaces

    def _assign_vlans_to_interfaces(self, interfaces):
        result = self._show_vlans()
        if result is None:
            return

        if isinstance(self.network_parser, HPNetworkOutputParser):
            vlans = self.network_parser.parse_vlans_from_global_info(result)

            for vlan in vlans:
                specific_result = self._show_vlan_detail(vlan.identifier)
                self.network_parser.associate_vlan_to_interfaces(
                    interfaces, vlan, specific_result)

        elif isinstance(self.network_parser, JuniperNetworkOutputParser):
            self.network_parser.associate_vlans_to_interfaces(
                interfaces, result)

    def _show_lldp_local_device(self):
        command = self.network_parser.lldp_local_cmd
        return self._send_ssh_command(command)

    def _show_lldp_neighbors(self):
        command = self.network_parser.lldp_neighbors_cmd
        return self._send_ssh_command(command)

    def _show_lldp_neighbor_detail(self, port):
        command = self.network_parser.lldp_neighbors_detail_cmd.format(port)
        return self._send_ssh_command(command)

    def _show_vlans(self):
        command = self.network_parser.vlans_global_cmd
        return self._send_ssh_command(command)

    def _show_vlan_detail(self, vlan_id):
        command = self.network_parser.vlans_specific_cmd.format(vlan_id)
        return self._send_ssh_command(command)

    def _show_virtual_machines(self):
        command = self.network_parser.vms_list_cmd
        return self._send_ssh_command(command)

    def _open_ssh_connection(self):
        """
        Opens a SSH connection (using paramiko) with the devices
        :param default: Using the default values for connection
        :type queue: bool
        :return: True if the connection succeeded
        :rtype: bool
        """
        self.attempts_count += 1

        try:
            username = self.ssh_username
            password = self.ssh_password
            pkey = None

            if self.device.is_linux_server():
                username = DEFAULT_USERNAME
                password = DEFAULT_PASSWORD
                pkey = self.ssh_private_key

            self.ssh.connect(hostname=self.hostname,
                             username=username,
                             password=password,
                             pkey=pkey,
                             timeout=self.ssh_timeout)
            self.shell = self.ssh.invoke_shell()
            self.shell.set_combine_stderr(True)

            logging.info("Connected to %s.", self.hostname)
            time.sleep(1)

            return True

        except paramiko.AuthenticationException as pae:
            # Retry a new connection with custom values
            if self.attempts_count < self.ssh_max_attempts:
                logging.debug("Authentication failed with %s.", self.hostname)
                return self._open_ssh_connection()
            else:
                logging.warning("Error with %s. %s", self.hostname, pae)

        except Exception as e:
            logging.warning("Error with %s. %s", self.hostname, e)

    def _close_ssh_connection(self):
        try:
            self.shell.close()
            self.ssh.close()
            logging.debug("Closed connection with %s.", self.hostname)
        except Exception as e:
            logging.warning("Could not close ssh connection with %s. %s",
                            self.hostname, e)

    def _send_ssh_command(self, command):
        """
        Sends a command to the device in order to retrieve the output data.
        :param command: The command to execute (must end by a '\\n')
        :type command: str
        :return: Returns the result from the command's output
        :rtype: str
        """
        try:

            logging.debug("Executing command '%s'...", command.rstrip())
            self.shell.send(command)

            receive_buffer = ""

            # Waiting for the server to display all the data
            while not self.network_parser.wait_string in receive_buffer:
                receive_buffer += self._receive_ssh_output()

            return receive_buffer

        except Exception as e:
            logging.warning("Could not send command to %s. %s",
                            self.hostname, e)

    def _prepare_switch(self):
        for cmd in self.network_parser.preparation_cmds:
            time.sleep(0.5)
            self._send_ssh_command(cmd)

    def _receive_ssh_output(self):
        if self.shell.recv_ready:
            time.sleep(0.1)
            raw_output = self.shell.recv(self.ssh_max_bytes)
            clean_output = self._remove_ansi_escape_codes(raw_output)
            return clean_output.decode('utf8')

    def _ignore(self, ip_address):
        for ip in self.ignore_list:
            if ip_address and ip_address.lower().startswith(ip.lower()):
                return True

    def _remove_ansi_escape_codes(self, string):
        expression = r"\[\d{1,2}\;\d{1,2}[a-zA-Z]?\d?|\[\??\d{1,2}[a-zA-Z]"
        ansi_escape = re.compile(expression)
        return ansi_escape.sub('', string.replace(u"\u001b", ""))

def _parse_args():
    parser = argparse.ArgumentParser(
        description="This program dynamically generates documentation for \
        the topology of a computing network by exploring every connected \
        switch using the LLDP protocol.")
    parser.add_argument("config", help="The configuration file.", type=str)

    return parser.parse_args()

def _initialize_logger(logfile):
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    # Console logging handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

    # File logging handler
    handler = logging.FileHandler(logfile, "w")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

def _write_results_to_file(results, outputfile):
    output = "["
    for key, value in results.items():
        output += "{0},\n".format(value.to_JSON())
    output = output[:-2] + "]"

    with open(outputfile, "w") as _file:
        _file.write(output.encode('utf8'))

def main():
    args = _parse_args()
    config_file = args.config

    if not os.path.isfile(config_file):
        logging.error("Could not find configuration file '%s'.", config_file)
        exit()

    config.read(config_file)

    protocol = config.get('DEFAULT', 'Protocol')
    source_address = config.get('DEFAULT', 'SourceAddress')
    outputfile = config.get('DEFAULT', 'OutputFile')
    logfile = config.get('DEFAULT', 'LogFile')

    _initialize_logger(logfile)

    queue = Queue()
    queue.put(Device(system_name=source_address))

    explored_devices = Manager().dict()

    start_time = time.time()

    if protocol != "LLDP":
        logging.error("Unsupported protocol '%s'.", protocol)

    jobs = []

    while True:
        # Starting a new process for each address added in the queue
        if not queue.empty():  # and len(jobs) < 10:
            nextDevice = queue.get()
            p = Process(
                target=NetworkExplorer(nextDevice).explore_lldp,
                args=(explored_devices, queue),
                name=nextDevice.system_name)
            jobs.append(p)
            p.start()

        # Removing every process who's finished
        for j in jobs:
            if not j.is_alive():
                jobs.remove(j)

        # We're done when there aren't any process left
        if len(jobs) == 0:
            break

    if len(explored_devices) > 0:
        _write_results_to_file(explored_devices, outputfile)

        logging.info("Found %s device(s) in %s second(s).",
                     len(explored_devices),
                     round(time.time() - start_time, 2))
    else:
        logging.warning("Could not find anything.")


if __name__ == "__main__":
    try:
        main()
    except ConfigParser.Error as cpe:
        logging.error("Configuration error. %s", cpe)
