#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

from NetworkObjects import *


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

    def build_vlans_from_global_info(self, global_result):
        raise NotImplementedError()

    def build_vlan_from_specific_info(self, specific_result):
        raise NotImplementedError()

    def attribute_lldp_remote_info(self, key, value):
        raise NotImplementedError()

    def attribute_lldp_local_info(self, key, value):
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
            .replace(u"\u001b", "")\
            .replace("[?25h", "")\
            .replace("[24;19H", "")


class HPNetworkDeviceBuilder(NetworkDeviceBuilder):
    def __init__(self):
        self.wait_string = "#"
        self.preparation_cmds = ["\n", "no page\n"]
        self.lldp_local_cmd = "show lldp info local-device\n"
        self.lldp_neighbors_cmd = "show lldp info remote-device\n"
        self.lldp_neighbors_detail_cmd = "show lldp info remote-device {0}\n"
        self.vlans_global_cmd = "show vlans\n"
        self.vlans_specific_cmd = "show vlans {0}\n"

    def build_device_from_lldp_local_info(self, lldp_result):
        device = NetworkDevice()

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    self.attribute_lldp_local_info(device, key, value)

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
            device = NetworkDevice()

            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    self.attribute_lldp_remote_info(device, key, value)

                elif '#' in line:
                    devices.append(device)
                    device = NetworkDevice()

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

    def build_vlans_from_global_info(self, global_result):
        vlans = []

        try:
            name_index = None
            status_index = None

            for rawline in global_result.splitlines():
                line = self.clean(rawline)

                targets = ["Name", "Status"]

                if all(t in line for t in targets):
                    name_index = line.find(targets[0])
                    status_index = line.find(targets[1])

                elif name_index is not None and status_index is not None and \
                    "----" not in line:

                    if line.strip() == "":
                        break

                    vlan_id = line[:name_index-1].strip()
                    vlan_name = line[name_index:status_index-1][:-1].strip()

                    vlan = Vlan(identifier=vlan_id, name=vlan_name)
                    vlans.append(vlan)

        except Exception as e:
            print("Could not extract vlans from '{0}'.".format(global_result))

        return vlans

    def asociate_vlan_with_interfaces(self, interfaces, vlan, specific_result):
        try:
            mode_index = None
            unknown_index = None
            status_index = None

            for rawline in specific_result.splitlines():
                line = self.clean(rawline)

                targets = ["Mode", "Unknown VLAN", "Status"]

                if all(t in line for t in targets):
                    mode_index = line.find(targets[0])
                    unknown_index = line.find(targets[1])
                    status_index = line.find(targets[2])

                elif mode_index is not None and unknown_index is not None and \
                   status_index is not None and "----" not in line:

                    if line.strip() == "":
                        break

                    interface_id = line[:mode_index-1].strip()
                    vlan_mode = line[mode_index:unknown_index-1].strip()
                    vlan_status = line[status_index:].strip()

                    vlan = Vlan\
                    (
                        identifier = vlan.identifier,
                        name = vlan.name,
                        mode = vlan_mode,
                        status = vlan_status
                    )

                    for interface in interfaces:
                        if interface.local_port == interface_id:
                            self._assign_vlan_to_interface(vlan, interface)

        except Exception as e:
            print("Could not extract vlans from '{0}'."
                  .format(specific_result))

        return vlan

    def _assign_vlan_to_interface(self, vlan, interface):
        for v in interface.vlans:
            if v.identifier == vlan.identifier:
                return

        interface.vlans.append(vlan)

    def attribute_lldp_remote_info(self, device, key, value):
        if "ChassisId" in key:
            device.mac_address = value
        elif "SysName" in key:
            device.system_name = value
        elif "System Descr" in key:
            device.system_description = value
        elif "System Capabilities Supported" in key:
            device.supported_capabilities = value
        elif "System Capabilities Enabled" in key:
            device.enabled_capabilities = value
        elif "Type" in key:
            device.ip_address_type = value
        elif "Address" in key:
            device.ip_address = value
        else:
            pass

    def attribute_lldp_local_info(self, device, key, value):
        if "Chassis Id" in key:
            device.mac_address = value
        elif "System Name" in key:
            device.system_name = value
        elif "System Description" in key:
            device.system_description = value
        elif "System Capabilities Supported" in key:
            device.supported_capabilities = value
        elif "System Capabilities Enabled" in key:
            device.enabled_capabilities = value
        elif "Type" in key:
            device.ip_address_type = value
        elif "Address" in key:
            device.ip_address = value
        else:
            pass

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
        device = NetworkDevice()

        try:
            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)
                if ':' in rawline:
                    key, value = self.extract_key_and_value_from_line(line)

                    self.attribute_lldp_local_info(device, key, value)

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
            device = NetworkDevice()

            for rawline in lldp_result.splitlines():
                line = self.clean(rawline)

                if "Neighbour Information" in line:
                    skip_line = False

                if not skip_line:
                    if ':' in line:
                        key, value = self.extract_key_and_value_from_line(line)

                        self.attribute_lldp_remote_info(device, key, value)

                    if "Address" in line:
                        devices.append(device)
                        device = NetworkDevice()
                        skip_line = True

        except Exception as e:
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

    def build_vlans_from_global_info(self, global_result):
        raise NotImplementedError()

    def build_vlan_from_specific_info(self, specific_result):
        raise NotImplementedError()

    def attribute_lldp_remote_info(self, device, key, value):
        if "Chassis ID" in key:
            device.mac_address = value.replace(':', ' ')
        elif "System name" in key:
            device.system_name = value
        elif "System Description" in key:
            device.system_description = value
        elif "Supported" in key:
            device.supported_capabilities = value
        elif "Enabled" in key:
            device.enabled_capabilities = value
        elif "Type" in key:
            device.ip_address_type = value
        elif "Address" in key:
            device.ip_address = value
        else:
            pass

    def attribute_lldp_local_info(self, device, key, value):
        if "Chassis ID" in key:
            device.mac_address = value.replace(':', ' ')
        elif "System name" in key:
            device.system_name = value
        elif "System descr" in key:
            device.system_description = value
        elif "Supported" in key:
            device.supported_capabilities = value
        elif "Enabled" in key:
            device.enabled_capabilities = value
#        elif "Type" in key:
#            device.ip_address_type = value
#        elif "Address" in key:
#            device.ip_address = value
        else:
            pass
            #print("Unexpected key '{0}'.".format(key))

    def extract_key_and_value_from_line(self, line):
        return NetworkDeviceBuilder.extract_key_and_value_from_line(line)

    def clean(self, string):
        return NetworkDeviceBuilder.clean(string)
