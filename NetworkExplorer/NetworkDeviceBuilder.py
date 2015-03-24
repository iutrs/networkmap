#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

from NetworkDevice import *


class NetworkDeviceBuilder(object):
    def __init__(self):
        raise NotImplementedError()

    def build_devices_from_lldp_remote_info(self, lldp_result):
        raise NotImplementedError()

    def build_device_from_lldp_local_info(self, lldp_result):
        raise NotImplementedError()

    def build_interfaces_from_lldp_remote_info(self, lldp_result):
        raise NotImplementedError()

    def build_interface_from_line(self, line):
        raise NotImplementedError()

    @staticmethod
    def get_builder_type(result):
        for rawline in result.splitlines():
            line = NetworkDeviceBuilder.clean(rawline)
            if "ProCurve" in line or "Hewlett-Packard" in line:
                return HPNetworkDeviceBuilder()
            elif "JUNOS" in line or "Juniper" in line:
                return JuniperNetworkDeviceBuilder()
            elif "Cisco" in line:
                return None

        print("Could not get builder type: ", result)

    @staticmethod
    def extract_key_and_value_from_line(line):
        tokens = line.split(':', 1)
        key = tokens[0].strip()
        value = tokens[1].strip()

        return (key, value)

    @staticmethod
    def clean(string):
        return string\
            .replace("[24;1H", "")\
            .replace("[1;24r", "")\
            .replace("[2K", "")\
            .replace(u"\u001b", "")


class HPNetworkDeviceBuilder(NetworkDeviceBuilder):
    def __init__(self):
        self.wait_string = "#"
        self.preparation_cmds = ["\n", "no page\n"]
        self.lldp_local_cmd = "show lldp info local-device\n"
        self.lldp_neighbors_cmd = "show lldp info remote-device\n"
        self.lldp_neighbors_detail_cmd = "show lldp info remote-device {0}\n"

    def build_device_from_lldp_local_info(self, lldp_result):
        device = HPNetworkDevice()

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    device.attribute_lldp_local_info(key, value)

                    if key == "Address":
                        break

        except Exception as e:
            device = None
            print("Could not build network device from '{0}'. {1}".format(
                  lldp_result, e))

        return device

    def build_devices_from_lldp_remote_info(self, lldp_result):
        devices = []

        try:
            currentDevice = HPNetworkDevice()

            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    currentDevice.attribute_lldp_remote_info(key, value)

                elif '#' in line:
                    devices.append(currentDevice)
                    currentDevice = HPNetworkDevice()

        except Exception as e:
            print("Could not build network devices from '{0}'. {1}".format(
                  lldp_result, e))

        return devices

    def build_interfaces_from_lldp_remote_info(self, lldp_result):
        interfaces = []

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if len(line) > 57 and line[12] == '|':
                    interface = self.build_interface_from_line(line)
                    if interface.local_port != 'LocalPort':
                        interfaces.append(interface)
        except Exception as e:
            print("Could not extract interfaces from '{0}'."
                  .format(lldp_result))

        return interfaces

    def build_interface_from_line(self, line):

        local_port = line[:11].strip()
        chassis_id = line[13:38].strip()
        port_descr = line[47:55].strip()
        sys_name = line[57:].strip()

        return NetworkDeviceInterface(local_port=local_port,
                                      remote_port=port_descr,
                                      remote_mac_address=chassis_id,
                                      remote_system_name=sys_name)

    def extract_key_and_value_from_line(self, line):
        return NetworkDeviceBuilder.extract_key_and_value_from_line(line)

    def clean(self, string):
        return NetworkDeviceBuilder.clean(string)


class JuniperNetworkDeviceBuilder(NetworkDeviceBuilder):
    def __init__(self):
        self.wait_string = ">"
        self.preparation_cmds = ["set cli screen-length 0\n",
                                 "set cli screen-width 0\n"]
        self.lldp_local_cmd = "show lldp local-information\n"
        self.lldp_neighbors_cmd = "show lldp neighbors\n"
        self.lldp_neighbors_detail_cmd = "show lldp neighbors interface {0}\n"

    def build_device_from_lldp_local_info(self, lldp_result):
        device = JuniperNetworkDevice()

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    device.attribute_lldp_local_info(key, value)

                    if key == "Enabled":
                        break

        except Exception as e:
            device = None
            print("Could not build network device from '{0}'. {1}".format(
                  lldp_result, e))

        return device

    def build_devices_from_lldp_remote_info(self, lldp_result):
        devices = []

        try:
            # The important information is between the lines containing
            # "Neighbour Information" and "Address".
            # We skip the lines until we find "Neighbour Information"
            # which indicates a new device is starting

            skip_line = True
            currentDevice = JuniperNetworkDevice()

            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)

                if "Neighbour Information" in line:
                    skip_line = False

                if not skip_line:
                    if ':' in line:
                        key, value = self.extract_key_and_value_from_line(line)

                        currentDevice.attribute_lldp_remote_info(key, value)

                    if "Address" in line:
                        devices.append(currentDevice)
                        currentDevice = JuniperNetworkDevice()
                        skip_line = True

        except Exception as e:
            print(e)
            print("Could not build network devices from '{0}'. {1}".format(
                  lldp_result, e))

        return devices

    def build_interfaces_from_lldp_remote_info(self, lldp_result):
        interfaces = []

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if len(line) > 73:
                    interface = self.build_interface_from_line(line)
                    if interface.local_port != "Local Interface":
                        interfaces.append(interface)
        except Exception as e:
            print("Could not extract interfaces from '{0}'."
                  .format(lldp_result))

        return interfaces

    def build_interface_from_line(self, line):

        local_port = line[:18].strip()
        chassis_id = line[39:58].strip().replace(':', ' ')
        port_descr = line[59:71].strip()
        sys_name = line[72:].strip()

        return NetworkDeviceInterface(local_port=local_port,
                                      remote_port=port_descr,
                                      remote_mac_address=chassis_id,
                                      remote_system_name=sys_name)

    def extract_key_and_value_from_line(self, line):
        return NetworkDeviceBuilder.extract_key_and_value_from_line(line)

    def clean(self, string):
        return NetworkDeviceBuilder.clean(string)
