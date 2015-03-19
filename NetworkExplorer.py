#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur    : Marc-Antoine Fortier
Date    : Mars 2015
"""

import os
import sys
import time
import socket

import argparse
import ConfigParser

import paramiko
import json

from multiprocessing import Process, Manager, Queue

import re

DEFAULT_MAX_BYTES = 2048*2048
DEFAULT_TIMEOUT = 10
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""

config = ConfigParser.RawConfigParser()


class NetworkDeviceInterface(object):
    def __init__(
            self,
            local_port=None,
            remote_port=None,
            remote_mac_address=None,
            remote_system_name=None,
            vlans=None):

        self.local_port = local_port
        self.remote_port = remote_port
        self.remote_mac_address = remote_mac_address
        self.remote_system_name = remote_system_name
        self.vlans = []

    def is_valid_lldp_interface(self):
        return \
            (
                self.remote_system_name is not None and
                self.remote_system_name != ""
            )

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)


class NetworkDevice(object):
    def __init__(
            self,
            mac_address=None,
            ip_address=None,
            ip_address_type=None,
            system_name=None,
            system_description=None,
            supported_capabilities=None,
            enabled_capabilities=None):

        self.mac_address = mac_address
        self.ip_address = ip_address
        self.ip_address_type = ip_address_type
        self.system_name = system_name
        self.system_description = system_description
        self.supported_capabilities = supported_capabilities
        self.enabled_capabilities = enabled_capabilities
        self.interfaces = []

    def attributeLLDPRemoteInformation(self, key, value):
        if "ChassisId" in key:
            self.mac_address = value
        elif "SysName" in key:
            self.system_name = value
        elif "System Descr" in key:
            self.system_description = value
        elif "System Capabilities Supported" in key:
            self.supported_capabilities = value
        elif "System Capabilities Enabled" in key:
            self.enabled_capabilities = value
        elif "Type" in key:
            self.ip_address_type = value
        elif "Address" in key:
            self.ip_address = value
        elif "Local Port" in key:
            pass
        elif "ChassisType" in key:
            pass
        elif "PortType" in key:
            pass
        elif "PortId" in key:
            pass
        elif "PortDescr" in key:
            pass
        elif "Pvid" in key:
            pass
        elif "EndpointClass" in key:
            pass
        else:
            print("Unexpected key '{0}'.".format(key))

    def attributeLLDPLocalInformation(self, key, value):
        if "Chassis Id" in key:
            self.mac_address = value
        elif "System Name" in key:
            self.system_name = value
        elif "System Description" in key:
            self.system_description = value
        elif "System Capabilities Supported" in key:
            self.supported_capabilities = value
        elif "System Capabilities Enabled" in key:
            self.enabled_capabilities = value
        elif "Type" in key:
            self.ip_address_type = value
        elif "Address" in key:
            self.ip_address = value
        elif "ChassisType" in key:
            pass
        elif "ManagementAddress" in key:
            pass
        else:
            print("Unexpected key '{0}'.".format(key))

    def is_valid_lldp_device(self):
        return \
            (
                self.enabled_capabilities is not None and
                "bridge" in self.enabled_capabilities and
                self.ip_address is not None and
                self.ip_address != "" and
                self.system_name is not None and
                self.system_name != ""
            )

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class NetworkDeviceBuilder(object):
    def __init__():
        pass

    @staticmethod
    def buildNetwordDevicesFromLLDPRemoteInformation(lldp_result):
        """
        Builds an array of NetworkDevice objects from the LLDP remote device \
        information detail of a Hewlett-Packard\xc2 switch.
        :param lldp_result: The result of the command "show lldp info remote-\
            device [port]"
        :type lldp_result: string
        :return: An array of the NetworkDevice objects built from the \
            provided result
        :rtype: NetworkDevice[]
        """
        devices = []

        try:
            currentDevice = NetworkDevice()

            for rawline in lldp_result.splitlines():
                line = NetworkDeviceBuilder._clean(rawline)
                if ':' in rawline:
                    key, value = NetworkDeviceBuilder\
                        ._extractKeyAndValueFromLine(line)

                    currentDevice.attributeLLDPRemoteInformation(key, value)

                elif '#' in line:
                    devices.append(currentDevice)
                    currentDevice = NetworkDevice()

        except Exception:
            print("Could not build network devices from '{0}'.".format(
                  lldp_result))

        return devices

    @staticmethod
    def buildNetwordDeviceFromLLDPLocalInformation(lldp_result):
        """
        Builds a NetworkDevice object from the LLDP local device \
        information detail of a Hewlett-Packard\xc2 switch.
        :param lldp_result: The result of the command "show lldp info \
            local-device"
        :type lldp_result: string
        :return: The NetworkDevice object built from the provided result
        :rtype: NetworkDevice
        """
        device = NetworkDevice()

        try:
            for rawline in lldp_result.splitlines():
                line = NetworkDeviceBuilder._clean(rawline)
                if ':' in rawline:
                    key, value = NetworkDeviceBuilder\
                        ._extractKeyAndValueFromLine(line)

                    device.attributeLLDPLocalInformation(key, value)

                    if key == "Address":
                        break

        except Exception:
            print("Could not build network device from '{0}'.".format(
                  lldp_result))

        return device

    @staticmethod
    def extractInterfacesFromLLDPRemoteInformation(lldp_result):
        """
        Builds an array containing the connected LLDP interfaces of a \
            Hewlett-Packard\xc2 switch.
        :param lldp_result: The result of the command "show lldp info \
            remote-device"
        :type lldp_result: string
        :return: An array of the of the connected interfaces built from the \
            provided result
        :rtype: NetworkDeviceInterface[]
        """
        interfaces = []

        try:
            for rawline in lldp_result.splitlines():
                line = NetworkDeviceBuilder._clean(rawline)
                if len(line) > 13 and line[12] == '|':
                    interface = NetworkDeviceBuilder\
                        ._buildInterfaceFromLine(line)
                    if interface.local_port != 'LocalPort':
                        interfaces.append(interface)
        except Exception as e:
            print("Could not extract interfaces from '{0}'."
                  .format(lldp_result))

        return interfaces

    @staticmethod
    def _buildInterfaceFromLine(line):

        local_port = line[:11].strip()
        chassis_id = line[13:38].strip()
        port_descr = line[47:55].strip()
        sys_name = line[57:].strip()

        return NetworkDeviceInterface(local_port=local_port,
                                      remote_port=port_descr,
                                      remote_mac_address=chassis_id,
                                      remote_system_name=sys_name)

    @staticmethod
    def _extractKeyAndValueFromLine(line):
        tokens = line.split(':')
        key = tokens[0].strip()
        value = tokens[1].strip()

        return (key, value)

    @staticmethod
    def _clean(string):
        return string\
            .replace("[24;1H", "")\
            .replace("[1;24r", "")\
            .replace("[2K", "")\
            .replace(u"\u001b", "")


class NetworkExplorer(object):
    def __init__(self):

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

    def explore_lldp(self, device, explored_devices, queue):
        """
        Explores a Hewlett-Packard\xc2 switch using the LLDP protocol in \
            order to add his valid neighbors in the queue.
        :param device: The NetworkDevice object representing a switch
        :type device: NetworkDevice
        :param explored_devices: The list of the devices already explored
        :type explored_devices: NetworkDevice[]
        :param queue: The queue of the next devices to explore
        :type queue: Queue()
        :return: None
        """

        if self._open_ssh_connection(device.ip_address):

            device = self._get_lldp_local_device()

            print("Extracting lldp information for {0}..."
                  .format(device.system_name))

            interfaces = self._get_lldp_interfaces()
            device.interfaces = interfaces

            neighbors = self._get_lldp_remote_devices(interfaces)

            self._close_ssh_connection()

            for neighbor in neighbors:
                if neighbor.is_valid_lldp_device() and \
                   neighbor.mac_address not in explored_devices:
                        explored_devices[neighbor.mac_address] = neighbor

                        if neighbor.ip_address not in self.ignore_list:
                            queue.put(neighbor)

        explored_devices[device.mac_address] = device

    def _get_lldp_local_device(self):
        command = "show lldp info local-device\n"
        device_info = self._send_ssh_command(command, True)

        return NetworkDeviceBuilder\
            .buildNetwordDeviceFromLLDPLocalInformation(device_info)

    def _get_lldp_interfaces(self):
        command = "show lldp info remote-device\n"
        remote_devices_list = self._send_ssh_command(command, False)

        return NetworkDeviceBuilder.extractInterfacesFromLLDPRemoteInformation(
            remote_devices_list)

    def _get_lldp_remote_devices(self, interfaces):
        devices_details = ""

        for interface in interfaces:
            if interface.is_valid_lldp_interface():
                command = "show lldp info remote-device {0}\n".format(
                    interface.local_port)

                result = self._send_ssh_command(command, False)
                if result is not None:
                    devices_details += result

        return NetworkDeviceBuilder\
            .buildNetwordDevicesFromLLDPRemoteInformation(devices_details)

    def _open_ssh_connection(self, hostname):
        success = False
        try:
            self.ssh.connect(hostname,
                             username=self.ssh_username,
                             password=self.ssh_password)
            self.shell = self.ssh.invoke_shell()
            self.shell.settimeout(self.ssh_timeout)

            print("Connected to {0}.".format(hostname))
            success = True
        except socket.error as se:
            print("Error with {0}. {1}".format(hostname, se))
        except paramiko.AuthenticationException as pae:
            print("Error with {0}. {1}".format(hostname, pae))
        except Exception as e:
            print("Unexpected error with: {0}. {1}".format(hostname, e))

        return success

    def _close_ssh_connection(self):
        try:
            self.shell.close()
            self.ssh.close()
        except Exception:
            print("Could not close ssh connection.")

    def _send_ssh_command(self, command, prepare):
        """
        Opens a SSH connection using paramiko with a Hewlett-Packard\xc2 \
        switch in order to retrieve the output data.
        :param command: The command to execute (ending by a '\\n')
        :type command: str
        :param prepare: Preparing the switch before the command
        :type prepare: bool
        :return: Returns the result from the command's output
        :rtype: str
        """
        result = None

        try:
            # These 'time.sleep()' are used to give enough time for the switch
            # to operate
            if prepare:
                time.sleep(1)
                self.shell.send('\n')  # Bypassing the HP switch welcome page
                time.sleep(0.5)
                self.shell.send('no page\n')  # Display all data at once
                time.sleep(0.5)

                self.shell.recv(self.ssh_max_bytes)  # Flushing useless data

            #print("Executing command '{0}'...".format(command.rstrip()))
            self.shell.send(command)

            # TODO Change for a while loop until we've got everything
            time.sleep(1.5)  # Waiting for the server to display all the data

            result = self.shell.recv(self.ssh_max_bytes)

        except socket.error as se:
            print("Socket error: {0}".format(se))
        except Exception as e:
            print("Unexpected error: {0}".format(e))

        return result


def _parseargs():
    parser = argparse.ArgumentParser(
        description="This program dynamically generates documentation for \
        the topology of a computing network by exploring every connected \
        switch using the LLDP protocol.")
    parser.add_argument("config", help="The configuration file.", type=str)

    return parser.parse_args()


def main():
    args = _parseargs()
    config_file = args.config

    if os.path.isfile(config_file):
        try:
            config.read(config_file)

            source_address = config.get('DEFAULT', 'SourceAddress')
            protocol = config.get('DEFAULT', 'Protocol')
            outputfile = config.get('DEFAULT', 'OutputFile')

            MarcoPolo = NetworkExplorer()

            origin = NetworkDevice(ip_address=source_address)
            explored_devices = Manager().dict()
            queue = Queue()

            if protocol == "LLDP":
                MarcoPolo.explore_lldp(origin, explored_devices, queue)

                jobs = []

                while True:
                    time.sleep(1)
                    if not queue.empty():  # and len(jobs) < 10:
                        nextDevice = queue.get()
                        p = Process(target=MarcoPolo.explore_lldp,
                                    args=(nextDevice, explored_devices, queue),
                                    name=nextDevice.system_name)
                        jobs.append(p)
                        p.start()

                    for j in jobs:
                        if not j.is_alive():
                            jobs.remove(j)

                    if len(jobs) == 0:
                        break

                print("Done")

            else:
                print("Unsupported protocol '{0}'.".format(protocol))

            if len(explored_devices) > 0:
                _file = open(outputfile, "w")

                for key, device in explored_devices.items():
                    _file.write("{0}\n".format(device.to_JSON()))

                    print("{0} has {1} connected interfaces."
                          .format(device.system_name, len(device.interfaces)))

                _file.close()

                print("Found {0} devices.".format(len(explored_devices)))

            else:
                print("Could not find anything.")

        except ConfigParser.Error as cpe:
            print("Configuration error. {0}".format(cpe))
        except Exception as e:
            print("Unexpected error in main. {0}".format(e))
    else:
        print("Could not find configuration file '{0}'.".format(config_file))

if __name__ == "__main__":
    main()
