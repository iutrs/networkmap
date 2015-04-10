#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import re
import time
import socket
import logging

from multiprocessing import Process, Manager, Queue

import paramiko

from NetworkOutputParser import *

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 1024
DEFAULT_MAX_ATTEMPTS = 1
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = None


class NetworkExplorer(object):
    def __init__(self,
                 device,
                 ignore_list=(),
                 ssh_timeout=DEFAULT_TIMEOUT,
                 ssh_max_bytes=DEFAULT_MAX_BYTES,
                 ssh_max_attempts=DEFAULT_MAX_ATTEMPTS,
                 ssh_username=DEFAULT_USERNAME,
                 ssh_password=DEFAULT_PASSWORD,
                 ssh_private_key=None):

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.shell = None

        self.attempts_count = 0
        self.network_parser = None

        self.device = device
        self.hostname = device.system_name

        self.ignore_list = ignore_list

        self.ssh_timeout = ssh_timeout
        self.ssh_max_bytes = ssh_max_bytes
        self.ssh_max_attempts = ssh_max_attempts
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key

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

        # Determining the type of the current device from the switch banner
        banner = self._receive_ssh_output()
        self.network_parser = NetworkOutputParser.get_parser_type(banner)

        if self.network_parser is None:
            logging.warning("Could not recognize device %s. Here is the \
                switch prompt: %s", self.hostname, switch_prompt)
            return

        # Preparing the switch, such as removing pagination
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

        vm_result = self._show_virtual_machines()
        device.virtual_machines = self.network_parser.parse_vms_list(vm_result)

        neighbors_result = self._show_lldp_neighbors()
        device.interfaces = self._get_lldp_interfaces(neighbors_result)

        if len(device.interfaces) > 0:
            neighbors_result = ""

        for interface in device.interfaces:
            if interface.is_valid_lldp_interface():
                port = interface.local_port
                partial_result = self._show_lldp_neighbor_detail(port)

                if partial_result is not None:
                    neighbors_result += partial_result

        neighbors = self.network_parser.parse_devices_from_lldp_remote_info(
            device, neighbors_result)

        return neighbors

    def _get_lldp_interfaces(self, lldp_result):
        interfaces = self.network_parser\
            .parse_interfaces_from_lldp_remote_info(lldp_result)

        self._assign_vlans_to_interfaces(interfaces)

        return interfaces

    def _assign_vlans_to_interfaces(self, interfaces):
        result = self._show_vlans()
        if result is None:
            return

        vlans = self.network_parser.parse_vlans_from_global_info(result)

        if len(vlans) == 0:
            self.network_parser.associate_vlans_to_interfaces(
                interfaces, result)

        for vlan in vlans:
            specific_result = self._show_vlan_detail(vlan.identifier)
            self.network_parser.associate_vlan_to_interfaces(
                interfaces, vlan, specific_result)

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
                             look_for_keys=False,
                             timeout=self.ssh_timeout)
            self.shell = self.ssh.invoke_shell()
            self.shell.set_combine_stderr(True)

            logging.info("Connected to %s.", self.hostname)
            time.sleep(1)

            return True

        except paramiko.AuthenticationException as pae:
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
        if command is None:
            return None

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
            return self._remove_ansi_escape_codes(raw_output.decode('utf8'))

    def _ignore(self, ip_address):
        for ip in self.ignore_list:
            if ip_address and ip_address.lower().startswith(ip.lower()):
                return True

    def _remove_ansi_escape_codes(self, string):
        expression = r"\[\d{1,2}\;\d{1,2}[a-zA-Z]?\d?|\[\??\d{1,2}[a-zA-Z]"
        ansi_escape = re.compile(expression)
        return ansi_escape.sub('', string.replace(u"\u001b", ""))
