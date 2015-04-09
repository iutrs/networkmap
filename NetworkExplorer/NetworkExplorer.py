#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import os
import sys
import time
import socket

import argparse
import ConfigParser

from multiprocessing import Process, Manager, Queue

import paramiko

from NetworkParser import *

DEFAULT_MAX_BYTES = 2048*2048
DEFAULT_TIMEOUT = 10
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""

config = ConfigParser.RawConfigParser()


class NetworkDeviceExplorer(object):
    def __init__(self, hostname):

        self.hostname = hostname
        self.prepare = True
        self.network_parser = None

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.shell = None

        self.ignore_list = ()

        self.ssh_timeout = DEFAULT_TIMEOUT
        self.ssh_max_bytes = DEFAULT_MAX_BYTES

        self.ssh_username = DEFAULT_USERNAME
        self.ssh_password = DEFAULT_PASSWORD

        try:
            self.ignore_list = config.get('DEFAULT', 'Ignore').split()

            self.ssh_timeout = config.getfloat('SSH', 'Timeout')
            self.ssh_max_bytes = config.getint('SSH', 'MaximumBytesToReceive')

            self.ssh_username = config.get('SSH', 'Username')
            self.ssh_password = config.get('SSH', 'Password')

        except ConfigParser.Error as cpe:
            print("Configuration error: {0}".format(cpe))
        except Exception as e:
            print("Unexpected error: {0}".format(e))

    def explore_lldp(self, explored_devices, queue):
        """
        Explores a device using the LLDP protocol in order to add its valid \
        neighbors in the queue.
        :param explored_devices: The dict of the devices already explored
        :type explored_devices: {str : NetworkDevice}
        :param queue: The queue of the next devices to explore
        :type queue: Queue()
        """
        try:
            self._open_ssh_connection()
            print("Connected to {0}.".format(self.hostname))
        except Exception as e:
            print("Could not open SSH connection to {0}: {1}".format(self.hostname, e))
            return
        
        time.sleep(1)

        # Determining the type of the current device from the switch prompt
        switch_prompt = self._receive_ssh_output()

        self.network_parser = NetworkParser.get_parser_type(switch_prompt)

        if self.network_parser is None:
            print("Could not recognize device {0}.".format(self.hostname))
            print("Here is the switch prompt: {0}".format(switch_prompt))
            return

        # Parsing device from local information
        local_info = self._show_lldp_local_device()
        device = self.network_parser.parse_device_from_lldp_local_info(
            local_info)

        if device is None or device.system_name is None:
            print("Could not parse device {0}.".format(self.hostname))
            return

        # We don't need to prepare the switch anymore
        self.prepare = False

        print("Discovering lldp neighbors for {0}..."
              .format(device.system_name))

        neighbors = self._get_lldp_neighbors(device)

        self._close_ssh_connection()

        for neighbor in neighbors:
            valid = neighbor.is_valid_lldp_device()
            explored = neighbor.mac_address in explored_devices

            if valid and not explored:
                explored_devices[neighbor.mac_address] = neighbor

                if not self._ignore(neighbor.ip_address) and \
                   not self._ignore(neighbor.system_name):
                    queue.put(neighbor.system_name)

        explored_devices[device.mac_address] = device

    def _get_lldp_neighbors(self, device):

        neighbors_result = self._show_lldp_neighbors()

        if isinstance(self.network_parser,
            (HPNetworkParser, JuniperNetworkParser)):

            device.interfaces = self._get_lldp_interfaces(neighbors_result)
            self._assign_vlans_to_interfaces(device.interfaces)

            neighbors_result = ""

            for interface in device.interfaces:
                if interface.is_valid_lldp_interface():

                    partial_result = self._show_lldp_neighbor_detail(
                        interface.local_port)
                    if partial_result is not None:
                        neighbors_result += partial_result

        elif isinstance(self.network_parser, LinuxNetworkParser):
            pass
            # TODO
            vms = self._show_vms()
            device.virtual_machines = self.network_parser.parse_vms_list(vms)

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

        if isinstance(self.network_parser, HPNetworkParser):
            vlans = self.network_parser.parse_vlans_from_global_info(result)

            for vlan in vlans:
                specific_result = self._show_vlan_detail(vlan.identifier)

                self.network_parser.associate_vlan_to_interfaces(
                    interfaces, vlan, specific_result)

        elif isinstance(self.network_parser, JuniperNetworkParser):
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

    def _show_vms(self):
        command = self.network_parser.vms_list_cmd
        return self._send_ssh_command(command)

    def _open_ssh_connection(self):
        """
        Opens a SSH connection (using paramiko) with the device in order to 
        retrieve the output data.
        """
        self.ssh.connect(hostname=self.hostname,
                         username=self.ssh_username,
                         password=self.ssh_password)
        self.shell = self.ssh.invoke_shell()
        self.shell.settimeout(self.ssh_timeout)
        self.shell.set_combine_stderr(True)

    def _close_ssh_connection(self):
        try:
            self.shell.close()
            self.ssh.close()
        except Exception as e:
            print("Could not close ssh connection with {0}. {1}"
                  .format(self.hostname, e))

    def _send_ssh_command(self, command):
        """
        Sends a command to the device in order to retrieve the output data.
        :param command: The command to execute (must end by a '\\n')
        :type command: str
        :return: Returns the result from the command's output
        :rtype: str
        """
        try:
            if self.prepare:
                self._prepare_switch()
                self._receive_ssh_output()

#            print("Executing command '{0}'...".format(command.rstrip()))
            self.shell.send(command)

            receive_buffer = ""

            # Waiting for the server to display all the data
            while not self.network_parser.wait_string in receive_buffer:
                receive_buffer += self._receive_ssh_output()

            return receive_buffer

        except socket.error as se:
            print("Socket error with {0}. {1}".format(self.hostname, se))
        except Exception as e:
            print("Unexpected error with {0}. {1}".format(self.hostname, e))

    def _prepare_switch(self):
        for cmd in self.network_parser.preparation_cmds:
            time.sleep(0.5)
            self.shell.send(cmd)

    def _receive_ssh_output(self):
        time.sleep(0.1)
        if self.shell.recv_ready:
            return self.shell.recv(self.ssh_max_bytes)

    def _ignore(self, ip_address):
        for ip in self.ignore_list:
            if ip_address and ip_address.lower().startswith(ip.lower()):
                return True


def _parse_args():
    parser = argparse.ArgumentParser(
        description="This program dynamically generates documentation for \
        the topology of a computing network by exploring every connected \
        switch using the LLDP protocol.")
    parser.add_argument("config", help="The configuration file.", type=str)

    return parser.parse_args()

def _write_results_to_file(results, outputfile):
    output = "["
    for key, value in results.items():
        output += "{0},\n".format(value.to_JSON())
    output = output[:-2] + "]"

    with open(outputfile, "w") as _file:
        _file.write(output)

def main():
    args = _parse_args()
    config_file = args.config

    if not os.path.isfile(config_file):
        print("Could not find configuration file '{0}'.".format(config_file))
        exit()

    config.read(config_file)

    protocol = config.get('DEFAULT', 'Protocol')
    source_address = config.get('DEFAULT', 'SourceAddress')
    outputfile = config.get('DEFAULT', 'OutputFile')

    queue = Queue()
    queue.put(source_address)

    explored_devices = Manager().dict()

    start_time = time.time()

    if protocol != "LLDP":
        print("Unsupported protocol '{0}'.".format(protocol))

    jobs = []

    while True:
        # Starting a new process for each address added in the queue
        if not queue.empty():  # and len(jobs) < 10:
            next_address = queue.get()
            p = Process(
                target=NetworkDeviceExplorer(next_address).explore_lldp,
                args=(explored_devices, queue),
                name=next_address)
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

        print("Found {0} device(s) in {1} second(s).".format(
              len(explored_devices), round(time.time() - start_time, 2)))
    else:
        print("Could not find anything.")

if __name__ == "__main__":
    try:
        main()
    except ConfigParser.Error as cpe:
        print("Configuration error. {0}".format(cpe))
