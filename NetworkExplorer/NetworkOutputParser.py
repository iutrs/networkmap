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

    def parse_vlans(self, result):
        """
        Example of "show vlans" command result:

         Status and Counters - VLAN Information

          Maximum VLANs to support : 128
          Primary VLAN : DEFAULT_VLAN
          Management VLAN :

          802.1Q VLAN ID Name         Status       Voice Jumbo
          -------------- ------------ ------------ ----- -----
          1              DEFAULT_VLAN Port-based   No    No
          52             rch iut sud  Port-based   No    No
          53             ens iutinfo  Port-based   No    No
          749            ipv6-info-in Port-based   No    No
          796            toip tel ill Port-based   Yes   No
          810            adm urs 2    Port-based   No    No
          948            iutrs-imprim Port-based   No    No
          2999           toip alcatel Port-based   Yes   No

        INFO2824-1#
        """
        vlans = []

        try:
            regex = "(?P<id>[0-9]+\ +)(?P<name>.{0,12}\ )(?P<status>\S+)"

            for line in result.splitlines():
                if self.wait_string in line:
                    continue

                match = re.search(regex, line)
                if match:
                    vlan_id = match.group("id").strip()
                    vlan_name = match.group("name").strip()
                    vlan_status = match.group("status").strip()

                    vlan = Vlan(identifier=vlan_id,
                                name=vlan_name,
                                status = vlan_status)
                    vlans.append(vlan)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

        return vlans

    def associate_vlans_to_interfaces(self, interfaces, result):
        pass

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

    def parse_vms_list(self, vm_result):
        return []

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
        self.trunks_list_cmd = "show lldp neighbors\n"
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

    def parse_vlans(self, result):
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

    def parse_trunks(self, trunks_result):
        """
        Example of "show lldp neighbors" command result:

        Local Interface    Parent Interface    Chassis Id          Port info
        ge-1/0/46.0        -                   00:0e:7f:6e:c1:20   23
        ge-0/0/37.0        -                   00:0f:fe:7d:7c:68   eth0
        ge-1/0/16.0        -                   00:1f:29:01:dc:b7   eth0
        ge-0/0/47.0        ae0.0               00:21:f7:1e:25:80   23
        ge-1/0/47.0        ae0.0               00:21:f7:1e:25:80   24
        ge-1/0/42.0        -                   00:23:7d:5a:2d:ae   eth1
        ge-1/0/43.0        -                   00:23:7d:5b:09:f4   eth1
        ge-1/0/44.0        -                   00:23:7d:a7:48:4a   eth1
        ge-1/0/38.0        -                   9c:8e:99:19:99:78   eth3

        {master:1}
        admin@info4200-1>
        """
        trunks = {}

        try:
            for line in trunks_result.splitlines():
                if len(line) > 38:
                    port = line[:18].strip()
                    name = line[19:38].strip()
                    if name in trunks:
                        trunks[name].ports.append(port)
                    elif name != "-" and name != "Parent Interface":
                        trunks[name] = Trunk(group=name,
                                             name=name,
                                             ports=[port])
        except Exception as e:
            logging.error("Could not parse trunks from : %s. (%s)",
                          trunks_result, e)

        return trunks

    def parse_vms_list(self, vm_result):
        return []

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
        self.vlans_global_cmd = "ifconfig\n"
        self.vlans_specific_cmd = "cat /sys/class/net/{0}/bonding/slaves\n"
        self.vms_list_cmd = "virsh list --all\n"

        self.trunks = {}

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

    def parse_vlans(self, result):
        """
        This parses the output of the vlans_global_cmd command.
        """
        vlans = []
        try:
            regex = "(?P<port>[A-z]+[0-9]*)(\.)(?P<vlan>[0-z]+)"

            for line in result.splitlines():
                match = re.search(regex, line)
                if match:
                    port = match.group("port")
                    vlan_id = match.group("vlan")

                    # We put the port as an identifier here because we will
                    # need to verify if it is a bonding in the function
                    # 'associate_vlans_to_interfaces()'
                    vlan = Vlan(identifier=port, name=vlan_id)
                    vlans.append(vlan)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

        return vlans

    def associate_vlans_to_interfaces(self, interfaces, result):
        pass

    def associate_vlan_to_interfaces(self, interfaces, vlan, result):
        """
        This parses the output of the vlans_specific_cmd command.
        """
        try:
            # Give back the good identifier to the vlan since we needed
            # an interface (not a vlan like the other devices) in order to
            # enter this function.
            ports_affected_by_vlan = [vlan.identifier]
            vlan.identifier = vlan.name
            vlan.name = None

            for line in result.splitlines():
                if "cat " in line or self.wait_string in line:
                    continue

                # If the interface is a bonding, the associated ports are
                # shown. Otherwise it gives an error or simply nothing.
                existing_bonding = "cat: " not in line and line != ""
                if existing_bonding:
                    ports = line.split()

                    # Since there aren't any command to show trunks on Linux,
                    # we store theses bonding to return them later in the 
                    # 'parse_trunks()' function
                    group = ports_affected_by_vlan[0] # The old vlan identifier
                    self.trunks[group] = Trunk(group=group, ports=ports)

                    ports_affected_by_vlan = ports

                for port in ports_affected_by_vlan:
                    for interface in interfaces:
                        if interface.local_port == port:
                            self._assign_vlan_to_interface(vlan, interface)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

    def parse_trunks(self, trunks_result):
        return self.trunks

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
        else:
            pass

    def _assign_vlan_to_interface(self, vlan, interface):
        return NetworkOutputParser.assign_vlan_to_interface(vlan, interface)

    def _extract_key_and_value_from_line(self, line):
        return NetworkOutputParser.extract_key_and_value_from_line(line)
