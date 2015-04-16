#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import re
import logging

from NetworkObjects import *


class NetworkOutputParser(object):
    def __init__(self):
        raise NotImplementedError()

    @staticmethod
    def get_parser_type(result):
        for line in result.splitlines():
            if any(d in line for d in HP_DEVICES):
                return HPNetworkOutputParser()
            elif any(d in line for d in JUNIPER_DEVICES):
                return JuniperNetworkOutputParser()
            elif any(d in line for d in LINUX_DEVICES):
                return LinuxNetworkOutputParser()
            elif "Cisco" in line:
                return None

    @staticmethod
    def assign_vlan_to_interface(vlan, interface):
        """Add the vlan to the interface if it doesnt already exists.
        :param vlan: The vlan to be assign
        :type vlan: Vlan()
        :param vlan: The interface
        :type interface: Interface()
        """
        for v in interface.vlans:
            if v.identifier == vlan.identifier:
                return

        interface.vlans.append(vlan)

    @staticmethod
    def extract_key_and_value_from_line(line):
        """Substring the key and the value separated from the first
         occurrence of ':' in the provided string
        :param line: The line as a string
        :type line: str
        :return: The extracted key and value
        :rtype: (str, str)
        """
        tokens = line.split(':', 1)
        key = tokens[0].strip()
        value = tokens[1].strip()

        return (key, value)


class HPNetworkOutputParser(NetworkOutputParser):
    """Parses the output of Hewlett-Packard switches."""
    def __init__(self):
        self.wait_string = "#"
        self.preparation_cmds = ["\n", "no page\n"]
        self.lldp_local_cmd = "show lldp info local-device\n"
        self.lldp_neighbors_cmd = "show lldp info remote-device\n"
        self.lldp_neighbors_detail_cmd = "show lldp info remote-device {0}\n"
        self.trunks_list_cmd = "show trunks\n"
        self.vlans_global_cmd = "show vlans\n"
        self.vlans_specific_cmd = "show vlans {0}\n"
        self.vms_list_cmd = None

    def parse_device_from_lldp_local_info(self, lldp_result):
        device = Device()

        try:
            for line in lldp_result.splitlines():
                if ':' in line:
                    key, value = self._extract_key_and_value_from_line(line)

                    self.attribute_lldp_local_info(device, key, value)

                    if key == "Address":
                        break

        except Exception as e:
            device = None
            logging.error("Could not parse network device from : %s. (%s)",
                          lldp_result, e)

        return device

    def parse_devices_from_lldp_remote_info(self, device, lldp_result):
        devices = []

        try:
            neighbor = Device()

            for line in lldp_result.splitlines():
                if ':' in line:
                    key, value = self._extract_key_and_value_from_line(line)

                    self.attribute_lldp_remote_info(neighbor, key, value)

                elif '#' in line:
                    devices.append(neighbor)
                    neighbor = Device()

        except Exception as e:
            logging.error("Could not parse network devices from : %s. (%s)",
                          lldp_result, e)

        return devices

    def parse_interfaces_from_lldp_remote_info(self, lldp_result):
        interfaces = []

        try:
            for line in lldp_result.splitlines():
                if len(line) > 57 and line[12] == '|':
                    interface = self._parse_interface_from_line(line)
                    if interface.local_port != 'LocalPort':
                        interfaces.append(interface)
        except Exception as e:
            logging.error("Could not extract interfaces from : %s. (%s)",
                          lldp_result, e)

        return interfaces

    def _parse_interface_from_line(self, line):

        local_port = line[:11].strip()
        chassis_id = line[13:38].strip()
        port_descr = line[47:55].strip()
        sys_name = line[57:].strip()

        return Interface(local_port=local_port,
                         remote_port=port_descr,
                         remote_mac_address=chassis_id,
                         remote_system_name=sys_name)

    def parse_vlans_from_global_info(self, global_result):
        vlans = []

        try:
            targets = ["Name", "Status"]
            name_index = None
            status_index = None

            for line in global_result.splitlines():
                if all(t in line for t in targets):
                    name_index = line.find(targets[0])
                    status_index = line.find(targets[1])
                elif "----" not in line and \
                     name_index is not None and status_index is not None and \
                     line.strip() != "" and not self.wait_string in line:

                    vlan_id = line[:name_index-1].strip()
                    vlan_name = line[name_index:status_index-1][:-1].strip()

                    vlan = Vlan(identifier=vlan_id, name=vlan_name)
                    vlans.append(vlan)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)",
                          global_result, e)

        return vlans

    def associate_vlan_to_interfaces(self, interfaces, vlan, specific_result):
        try:
            mode_index = None
            unknown_index = None
            status_index = None
            indexes = [None]

            for line in specific_result.splitlines():
                targets = ["Mode", "Unknown VLAN", "Status"]

                if all(t in line for t in targets):
                    mode_index = line.find(targets[0])
                    unknown_index = line.find(targets[1])
                    status_index = line.find(targets[2])
                    indexes = [mode_index, unknown_index, status_index]

                elif "----" not in line and line.strip() != "" and not \
                     self.wait_string in line and \
                     all(t is not None for t in indexes):

                    interface_id = line[:mode_index-1].strip()
                    vlan_mode = line[mode_index:unknown_index-1].strip()
                    vlan_status = line[status_index:].strip()

                    new_vlan = Vlan(identifier=vlan.identifier,
                                    name=vlan.name,
                                    mode=vlan_mode,
                                    status=vlan_status)

                    for interface in interfaces:
                        if interface.local_port == interface_id:
                            self._assign_vlan_to_interface(new_vlan, interface)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)",
                          specific_result, e)

    def parse_vms_list(self, vm_result):
        return []

    def parse_trunks(self, trunks_result):
        """
        Example of "show trunks" command result:

         Load Balancing

          Port | Name                             Type      | Group Type 
          ---- + -------------------------------- --------- + ----- -----
          A13  | SERVEURS                         100/1000T | Trk3  Trunk
          A14  | SERVEURS                         100/1000T | Trk3  Trunk
          A15  | BC                               100/1000T | Trk1  Trunk
          A16  | BC                               100/1000T | Trk1  Trunk
          B4   | fo INFOCOM 1                     1000SX    | Trk2  Trunk
          C4   | fo INFOCOM 2                     1000SX    | Trk2  Trunk

        CENTRAL5304-1#
        """

        trunks = {}
        try:
            regex = "(?P<port>\ +[0-z]{1,3}\ +)(\|)(?P<name>.{1,33}\ +)"
            regex += "(?P<type>.{1,9})( \| )(?P<group>.{1,5})"

            start = False
            for line in trunks_result.splitlines():

                match = re.search(regex, line)
                if match:
                    port = match.group("port").strip()
                    name = match.group("name").strip()
                    type = match.group("type").strip()
                    group = match.group("group").strip()

                    if group in trunks:
                        trunks[group].ports.append(port)
                    else:
                        trunks[group] = Trunk(group=group, name=name,
                                              type=type, ports=[port])

        except Exception as e:
            logging.error("Could not parse trunk from : %s. (%s)",
                          trunks_result, e)

        return trunks

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

    def _assign_vlan_to_interface(self, vlan, interface):
        return NetworkOutputParser.assign_vlan_to_interface(vlan, interface)

    def _extract_key_and_value_from_line(self, line):
        return NetworkOutputParser.extract_key_and_value_from_line(line)


class JuniperNetworkOutputParser(NetworkOutputParser):
    """Parses the output of Juniper switches."""
    def __init__(self):
        self.wait_string = ">"
        self.preparation_cmds = ["set cli screen-length 0\n",
                                 "set cli screen-width 0\n"]
        self.lldp_local_cmd = "show lldp local-information\n"
        self.lldp_neighbors_cmd = "show lldp neighbors\n"
        self.lldp_neighbors_detail_cmd = "show lldp neighbors interface {0}\n"
        self.trunks_list_cmd = None
        self.vlans_global_cmd = "show vlans detail\n"
        self.vlans_specific_cmd = None
        self.vms_list_cmd = None

    def parse_device_from_lldp_local_info(self, lldp_result):
        device = Device()

        try:
            for line in lldp_result.splitlines():
                if ':' in line:
                    key, value = self._extract_key_and_value_from_line(line)

                    self.attribute_lldp_local_info(device, key, value)

                    if key == "Enabled":
                        break

        except Exception as e:
            device = None
            logging.error("Could not parse network device from : %s. (%s)",
                          lldp_result, e)

        return device

    def parse_devices_from_lldp_remote_info(self, device, lldp_result):
        devices = []

        try:
            # The important information is between the lines containing
            # "Neighbour Information" and "Address".
            # We skip the lines until we find "Neighbour Information"
            # which indicates a new device is starting

            skip_line = True
            neighbor = Device()

            for line in lldp_result.splitlines():
                if "Neighbour Information" in line:
                    skip_line = False

                if ':' in line and not skip_line:
                    key, value = self._extract_key_and_value_from_line(line)

                    self.attribute_lldp_remote_info(neighbor, key, value)

                if "Address" in line and not skip_line:
                    devices.append(neighbor)
                    neighbor = Device()
                    skip_line = True

        except Exception as e:
            logging.error("Could not parse network devices from : %s. (%s)",
                          lldp_result, e)

        return devices

    def parse_interfaces_from_lldp_remote_info(self, lldp_result):
        interfaces = []

        try:
            for line in lldp_result.splitlines():
                if len(line) > 73:
                    interface = self._parse_interface_from_line(line)
                    if interface.local_port != "Local Interface":
                        interfaces.append(interface)
        except Exception as e:
            logging.error("Could not extract interfaces from : %s. (%s)",
                          lldp_result, e)

        return interfaces

    def _parse_interface_from_line(self, line):

        local_port = line[:18].strip()
        chassis_id = line[39:58].strip().replace(':', ' ')
        port_descr = line[59:71].strip()
        sys_name = line[72:].strip()

        return Interface(local_port=local_port,
                         remote_port=port_descr,
                         remote_mac_address=chassis_id,
                         remote_system_name=sys_name)

    def parse_vlans_from_global_info(self, global_result):
        return []

    def associate_vlans_to_interfaces(self, interfaces, result):
        try:
            vlan = Vlan()

            for line in result.splitlines():

                targets = ["VLAN: ", "Tag: "]

                if all(t in line for t in targets):
                    tokens = line.split(',')
                    vlan_name = tokens[0].split(targets[0])[1]
                    vlan_tag = tokens[1].split(targets[1])[1]

                    vlan.name = vlan_name
                    vlan.identifier = vlan_tag

                elif "agged interfaces:" in line:

                    vlan.mode = VlanMode.TRUNK
                    if "Untagged" in line:
                        vlan.mode = VlanMode.ACCESS

                    start_index = line.find(':') + 1
                    ports = line[start_index:].replace(' ', '').split(',')

                    if "None" not in line:
                        for p in ports:
                            if p[-1:] == '*':
                                p = p[:-1]
                                vlan.status = VlanStatus.ACTIVE
                            else:
                                vlan.status = VlanStatus.INACTIVE

                        for interface in interfaces:
                            if interface.local_port == p:
                                self._assign_vlan_to_interface(vlan, interface)

                    if "Tagged" in line:
                        vlan = Vlan()

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

    def parse_vms_list(self, vm_result):
        return []

    def parse_trunks(self, trunks_result):
        return {}

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
        else:
            pass

    def _assign_vlan_to_interface(self, vlan, interface):
        return NetworkOutputParser.assign_vlan_to_interface(vlan, interface)

    def _extract_key_and_value_from_line(self, line):
        return NetworkOutputParser.extract_key_and_value_from_line(line)


class LinuxNetworkOutputParser(NetworkOutputParser):
    """Parses the output of Linux servers."""
    def __init__(self):
        self.wait_string = "#"
        self.preparation_cmds = []
        self.lldp_local_cmd = None
        self.lldp_neighbors_cmd = "lldpctl\n"
        self.lldp_neighbors_detail_cmd = None
        self.trunks_list_cmd = None
        self.vlans_global_cmd = None
        self.vlans_specific_cmd = None
        self.vms_list_cmd = "virsh list --all\n"

    def parse_device_from_lldp_local_info(self, lldp_result):
        #TODO
        return Device()

    def parse_devices_from_lldp_remote_info(self, device, lldp_result):
        devices = []
        try:
            neighbor = Device()
            interface = Interface()
            line_count = 0

            for line in lldp_result.splitlines():

                line_count += 1
                if ':' in line and line_count > 3:
                    key, value = self._extract_key_and_value_from_line(line)
                    self.attribute_lldp_remote_info(neighbor, interface, key,
                                                    value)
                elif "----" in line and line_count > 3:
                    if interface.is_valid_lldp_interface():
                        device.interfaces.append(interface)
                        interface = Interface()

                    devices.append(neighbor)
                    neighbor = Device()

        except Exception as e:
            logging.error("Could not extract devices from : %s. (%s)",
                          lldp_result, e)

        return devices

    def parse_interfaces_from_lldp_remote_info(self, lldp_result):
        return []

    def parse_vms_list(self, vm_result):
        vms = []
        try:
            name_index = None
            state_index = None
            targets_en = [u"Name", u"State"]
            targets_fr = [u"Nom", u"État"]

            for line in vm_result.splitlines():
                if all(t in line for t in targets_en):
                    name_index = line.find(targets_en[0])
                    state_index = line.find(targets_en[1])

                elif all(t in line for t in targets_fr):
                    name_index = line.find(targets_fr[0])
                    state_index = line.find(targets_fr[1])

                elif "----" not in line and self.wait_string not in line and \
                     all(t is not None for t in[name_index, state_index]):

                    identifier = line[:name_index-1].strip()
                    name = line[name_index:state_index-1].strip()
                    state = line[state_index:].strip()

                    vm = VirtualMachine(identifier=identifier,
                                        name=name,
                                        state=state)
                    if vm.is_valid():
                        vms.append(vm)

        except Exception as e:
            logging.error("Could not extract virtual machines from : %s. (%s)",
                          vm_result, e)

        return vms

    def parse_trunks(self, trunks_result):
        return {}

    def attribute_lldp_remote_info(self, device, interface, key, value):
        if "Interface" in key:
            interface.local_port = value[:value.find(',')]
        elif "ChassisID" in key:
            mac = value.replace('mac ', '').replace(':', ' ')
            device.mac_address = mac
            interface.remote_mac_address = mac
        elif "SysName" in key:
            device.system_name = value
            interface.remote_system_name = value
        elif "SysDescr" in key:
            device.system_description = value
        elif "Capability" in key and "," in value:
            tokens = value.split()
            if "on" in tokens[1]:
                device.enabled_capabilities += tokens[0]
            device.supported_capabilities += tokens[0]
        elif "PortDescr" in key:
            interface.remote_port = value
        elif "VLAN" in key:
            tokens = value.replace(',', '').split()
            vlan = Vlan(identifier=tokens[0], name=tokens[1])
            self._assign_vlan_to_interface(vlan, interface)
        else:
            pass

    def _assign_vlan_to_interface(self, vlan, interface):
        return NetworkOutputParser.assign_vlan_to_interface(vlan, interface)

    def _extract_key_and_value_from_line(self, line):
        return NetworkOutputParser.extract_key_and_value_from_line(line)
