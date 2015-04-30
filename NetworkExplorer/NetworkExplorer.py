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
from auth_manager import AuthManager, AuthConfigError, NoAuthRequested

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 1024
DEFAULT_MAX_ATTEMPTS = 1


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

        try:
            self._open_ssh_connection()
        except NoAuthRequested as e:
            logging.info("[%s] No auth requested", self.hostname)
            self.device.status = DeviceStatus.NO_AUTH_REQUESTED
            return
        except paramiko.AuthenticationException as pae:
            logging.error("[%s] Authentication failed: %s", self.hostname, pae)
            self.device.status = DeviceStatus.AUTH_FAILED
            return
        except Exception as e:
            logging.error("[%s] Could not open SSH connection: %s",
                self.hostname, e)
            self.device.status = DeviceStatus.UNREACHABLE
            return
        finally:
            if self.device.mac_address:
                explored_devices[self.device.mac_address] = self.device

        # Determining the type of the current device from the switch banner
        banner = self._receive_ssh_output()
        self.network_parser = NetworkOutputParser.get_parser_type(banner)

        if self.network_parser is None:
            logging.warning(
                "[%s] Unsupported device type. Prompt was: %s",
                self.hostname, switch_prompt)
            return

        # Preparing the switch, such as removing pagination
        self._prepare_switch()

        # Building current device's informations if missing
        if self.device is None or self.device.mac_address is None:
            local_report = self._get_lldp_local_report()
            try:
                self.device = self.network_parser.\
                    parse_device_from_lldp_local_info(local_report)
                if not self.device.mac_address:
                    raise ValueError()
            except Exception as e:
                logging.error(
                    "[%s] Unable to parse lldp local report using %s: %s",
                    self.hostname,
                    self.network_parser.__class__.__name__,
                    e)
                return

        neighbors = self._build_lldp_neighbors(self.device)

        vlans_result = self._get_vlans()
        self._assign_vlans_to_interfaces(vlans_result)

        trunks_result = self._get_trunks()
        self.device.trunks = self.network_parser.parse_trunks(
            self.device.interfaces,
            trunks_result)

        vm_result = self._get_virtual_machines()
        self.device.virtual_machines = self.network_parser.parse_vms_list(
            vm_result)

        self._close_ssh_connection()

        explored_devices[self.device.mac_address] = self.device

        for neighbor in neighbors:
            valid = neighbor.is_valid_lldp_device()
            explored = neighbor.mac_address in explored_devices

            if valid and not explored:
                explored_devices[neighbor.mac_address] = neighbor
                queue.put(neighbor)

    def _build_lldp_neighbors(self, device):
        """
        Obtain the list of all lldp neighbors
        """
        lldp_neighbors_summary = self._get_lldp_neighbors()
        device.interfaces = self.network_parser\
            .parse_interfaces_from_lldp_remote_info(lldp_neighbors_summary)

        if len(device.interfaces) == 0:
            neighbors = []
            return neighbors

        # With lldpd on Linux, the lldp summary already contains all details
        if self.network_parser.lldp_neighbors_detail_cmd is None:
            neighbors = self.network_parser.parse_devices_from_lldp_remote_info(
                device, lldp_neighbors_summary)
        else:
            lldp_neighbors_details = []
            for interface in device.interfaces.values():
                if interface.is_valid_lldp_interface():
                    port = interface.local_port
                    detail = self._get_lldp_neighbor_detail(port)
                    lldp_neighbors_details.append(detail)

            neighbors = self.network_parser.parse_devices_from_lldp_remote_info(
                device, lldp_neighbors_details)

        return neighbors

    def _assign_vlans_to_interfaces(self, vlans_result):
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
                self.device.interfaces, vlans_result)

        # Other devices need to get specific information from each vlan before
        # assigning it one by one to the interfaces
        for vlan in vlans.values():
            detail_str = self.network_parser.get_vlan_detail_str(vlan)
            specific_result = self._get_vlan_detail(detail_str)
            self.network_parser.associate_vlan_to_interfaces(
                self.device.interfaces, vlan, specific_result)

    def _get_lldp_local_report(self):
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

        kwargs = self._auth_manager.get_params(self.hostname, self.device.type)

        kwargs.update({
            "hostname": self.hostname,
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": self.ssh_timeout})

        nb_attempts = 0
        while nb_attempts <= 3:
            try:
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh.connect(**kwargs)
            except paramiko.AuthenticationException as pae:
                raise # Do not retry if authentication failed
            except Exception as e:
                nb_attempts += 1
            else:
                break

        self.shell = self.ssh.invoke_shell()
        self.shell.set_combine_stderr(True)

        logging.info("[%s] SSH connection established", self.hostname)
        time.sleep(1)

    def _close_ssh_connection(self):
        """
        Closes the connection with the current device. That connection must
        have been opened beforehand.
        """
        try:
            self.shell.close()
            self.ssh.close()
            logging.debug("[%s] SSH connection closed", self.hostname)
        except Exception as e:
            logging.error("[%s] Could not close ssh connection: %s",
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
            logging.debug("[%s] Sending: %s", self.hostname, repr(command))
            self.shell.send(command)

            receive_buffer = ""
            wait_string = self.network_parser.wait_string
            length_when_mark_detected = 0
            empty_buffer_count = 0
            while True:
                temp_buffer = self._receive_ssh_output()
                receive_buffer += temp_buffer
                if not temp_buffer:
                    empty_buffer_count += 1
                else:
                    empty_buffer_count = 0

                if wait_string in receive_buffer[length_when_mark_detected:]:
                    length_when_mark_detected = len(receive_buffer)

                if length_when_mark_detected > 0 and empty_buffer_count == 3:
                    break

                time.sleep(0.1)

            logging.debug("[%s] Got response (len=%d)", self.hostname, length_when_mark_detected)
            return receive_buffer

        except Exception as e:
            logging.warning("[%s] Could not send command '%s': %s",
                self.hostname, command, e)

    def _receive_ssh_output(self):
        """
        Receives the raw output from the device after a command has been
        sent and cleans it before returning.

        :return: Returns the cleaned output of the device
        :rtype: str
        """
        if self.shell.recv_ready():
            raw_output = self.shell.recv(self.ssh_max_bytes)
            return self._remove_ansi_escape_codes(raw_output.decode('utf8'))
        else:
            return ""

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

    def _prepare_switch(self):
        """
        Sends the preparation commands to the device such as pressing
        a key to skip the banner or as removing pagination.
        """
        for cmd in self.network_parser.preparation_cmds:
            time.sleep(0.5)
            self._send_ssh_command(cmd)
