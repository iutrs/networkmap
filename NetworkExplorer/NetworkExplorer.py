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

import paramiko

from NetworkOutputParser import *
from auth_manager import AuthManager, AuthConfigError

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 1024
DEFAULT_MAX_ATTEMPTS = 1


class NoAuthRequested(Exception):
    pass


class NetworkExplorer(object):
    """
    This class will communicate with its assigned device in order to get
    the device's networking information such as its LLDP neighbors.
    """

    def __init__(self,
                 device,
                 parser,
                 ssh_timeout=DEFAULT_TIMEOUT,
                 ssh_max_bytes=DEFAULT_MAX_BYTES,
                 ssh_max_attempts=DEFAULT_MAX_ATTEMPTS):

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.shell = None

        self.attempts_count = 0
        self.network_parser = None

        self.device = device
        self.hostname = device.system_name

        self.ssh_timeout = ssh_timeout
        self.ssh_max_bytes = ssh_max_bytes
        self.ssh_max_attempts = ssh_max_attempts

        self._auth_manager = AuthManager(parser)

    def explore_lldp(self, explored_devices, queue):
        """
        Explores a device using the LLDP protocol in order to add its
        valid neighbors in the queue.

        :param explored_devices: The dict of the devices already explored
        :type explored_devices: {str : Device}
        :param queue: The queue of the next devices to explore
        :type queue: Queue()
        """

        # TODO Try new attempts when authentication fails
        try:
            self._open_ssh_connection()
        except NoAuthRequested as e:
            logging.info("No auth requested for %s", self.hostname)
            return
        except paramiko.AuthenticationException as pae:
            logging.warning("Authentication failed with %s.", self.hostname)
            return
        except Exception as e:
            logging.error("Error with %s: %s", self.hostname, e)
            return

        # Determining the type of the current device from the switch banner
        banner = self._receive_ssh_output()
        self.network_parser = NetworkOutputParser.get_parser_type(banner)

        if self.network_parser is None:
            logging.warning("Unsupported device type for %s. Prompt was: %s",
                self.hostname, switch_prompt)
            return

        # Preparing the switch, such as removing pagination
        self._prepare_switch()

        # Building current device's informations if missing
        if self.device is None or self.device.mac_address is None:
            self.device = self._build_current_device()

        if self.device is None or self.device.mac_address is None:
            logging.warning("Could not build device %s from its"
                "local lldp information.", self.hostname)
            return

        logging.info("Discovering lldp neighbors for %s...", self.hostname)

        neighbors = self._build_lldp_neighbors(self.device)

        self._close_ssh_connection()

        explored_devices[self.device.mac_address] = self.device

        for neighbor in neighbors:
            valid = neighbor.is_valid_lldp_device()
            explored = neighbor.mac_address in explored_devices

            if valid and not explored:
                explored_devices[neighbor.mac_address] = neighbor
                queue.put(neighbor)

    def _build_current_device(self):
        info = self._get_lldp_local_device()
        device = self.network_parser.parse_device_from_lldp_local_info(info)
        return device

    def _build_lldp_neighbors(self, device):
        """
        Obtain the list of all lldp neighbors
        """
        neighbors_result = self._get_lldp_neighbors()
        device.interfaces = self.network_parser\
            .parse_interfaces_from_lldp_remote_info(neighbors_result)

        if len(device.interfaces) > 0:
            neighbors_result = ""

        for interface in device.interfaces.values():
            if interface.is_valid_lldp_interface():
                port = interface.local_port
                partial_result = self._get_lldp_neighbor_detail(port)

                if partial_result is not None:
                    neighbors_result += partial_result

        neighbors = self.network_parser.parse_devices_from_lldp_remote_info(
            device, neighbors_result)

        # TODO Move this to other functions?
        vlans_result = self._get_vlans()
        self._assign_vlans_to_interfaces(device.interfaces, vlans_result)

        trunks_result = self._get_trunks()
        device.trunks = self.network_parser.parse_trunks(device.interfaces,
                                                         trunks_result)

        vm_result = self._get_virtual_machines()
        device.virtual_machines = self.network_parser.parse_vms_list(vm_result)
        # TODO

        return neighbors

    def _assign_vlans_to_interfaces(self, interfaces, vlans_result):
        """
        Parse the vlans result and assign them to the interfaces.
        """
        if vlans_result is None:
            return

        vlans = self.network_parser.parse_vlans(vlans_result)

        if len(vlans) == 0:
            # Some devices do not need to parse vlans from the global info and
            # can assign the vlans directly to interfaces from the first result
            self.network_parser.associate_vlans_to_interfaces(
                interfaces, vlans_result)

        # Other devices need to get specific information from each vlan before
        # assigning it one by one to the interfaces
        for vlan in vlans.values():
            detail_str = self.network_parser.get_vlan_detail_str(vlan)
            specific_result = self._get_vlan_detail(detail_str)
            self.network_parser.associate_vlan_to_interfaces(
                interfaces, vlan, specific_result)

    def _get_lldp_local_device(self):
        command = self.network_parser.lldp_local_cmd
        return self._send_ssh_command(command)

    def _get_lldp_neighbors(self):
        command = self.network_parser.lldp_neighbors_cmd
        return self._send_ssh_command(command)

    def _get_lldp_neighbor_detail(self, port):
        command = self.network_parser.lldp_neighbors_detail_cmd.format(port)
        return self._send_ssh_command(command)

    def _get_trunks(self):
        command = self.network_parser.trunks_list_cmd
        return self._send_ssh_command(command)

    def _get_vlans(self):
        command = self.network_parser.vlans_global_cmd
        return self._send_ssh_command(command)

    def _get_vlan_detail(self, vlan_id):
        command = self.network_parser.vlans_specific_cmd.format(vlan_id)
        return self._send_ssh_command(command)

    def _get_virtual_machines(self):
        command = self.network_parser.vms_list_cmd
        return self._send_ssh_command(command)

    def _open_ssh_connection(self):
        """
        Opens a SSH connection with the device
        """
        self.attempts_count += 1

        kwargs = self._auth_manager.get_params(self.hostname, self.device.type)

        if kwargs is None:
            raise NoAuthRequested("No auth method")

        kwargs.update({
            "hostname": self.hostname,
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": self.ssh_timeout})

        self.ssh.connect(**kwargs)
        self.shell = self.ssh.invoke_shell()
        self.shell.set_combine_stderr(True)

        logging.info("Connected to %s.", self.hostname)
        time.sleep(1)

    def _close_ssh_connection(self):
        """
        Closes the connection with the current device. That connection must
        have been opened beforehand.
        """
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
        :return: Returns the (clean) result from the command's output
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
        """
        Sends the preparation commands to the device such as pressing
        a key to skip the banner or as removing pagination.
        """
        for cmd in self.network_parser.preparation_cmds:
            time.sleep(0.5)
            self._send_ssh_command(cmd)

    def _receive_ssh_output(self):
        """
        Receives the raw output from the device after a command has been
        sent and cleans it before returning.

        :return: Returns the cleaned output of the device
        :rtype: str
        """
        if self.shell.recv_ready:
            time.sleep(0.1)
            raw_output = self.shell.recv(self.ssh_max_bytes)
            return self._remove_ansi_escape_codes(raw_output.decode('utf8'))

    def _remove_ansi_escape_codes(self, string):
        """
        Cleans a string by removing all ANSI and VT100 escape characters
        using a regular expression.

        :param string: The string to clean
        :type string: str
        :return: Returns the cleaned string
        :rtype: str
        """
        expression = r"\[\d{1,2}\;\d{1,2}[a-zA-Z]?\d?|\[\??\d{1,2}[a-zA-Z]"
        ansi_escape = re.compile(expression)
        return ansi_escape.sub('', string.replace(u"\u001b", ""))
