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

    def parse_device_from_lldp_local_info(self, result):
        raise NotImplementedError()

    def parse_devices_from_lldp_remote_info(self, device, result):
        raise NotImplementedError()

    def parse_interfaces_from_lldp_remote_info(self, result):
        raise NotImplementedError()

    def parse_vlans(self, result):
        raise NotImplementedError()

    def associate_vlans_to_interfaces(self, interfaces, result):
        raise NotImplementedError()

    def associate_vlan_to_interfaces(self, interfaces, vlan, specific_result):
        raise NotImplementedError()

    def parse_trunks(self, interfaces, trunks_result):
        raise NotImplementedError()

    def parse_vms_list(self, vm_result):
        raise NotImplementedError()

    def _parse_interface_from_line(self, line):
        raise NotImplementedError()

    def _extract_key_and_value_from_line(self, line):
        tokens = line.split(':', 1)
        key = tokens[0].strip()
        value = tokens[1].strip()

        return (key, value)

    def _attribute_lldp_local_info(self, device, key, value):
        raise NotImplementedError()

    def _attribute_lldp_remote_info(self, device, key, value):
        raise NotImplementedError()


class CommonSwitchParser(NetworkOutputParser):
    def parse_devices_from_lldp_remote_info(self, device, neighbors_details):
        devices = []

        for detail in neighbors_details:
            neighbor = Device()
            for line in detail.splitlines():
                if ':' in line:
                    try:
                        key, value = self._extract_key_and_value_from_line(line)
                        self._attribute_lldp_remote_info(neighbor, key, value)
                    except Exception as e:
                        print e
                        logging.error(
                            "Could not parse network devices from %s:%s",
                            detail, e)
            devices.append(neighbor)

        return devices


class HPNetworkOutputParser(CommonSwitchParser):
    """Parses the output of Hewlett-Packard switches."""
    def __init__(self):
        self.wait_string = "# "
        self.preparation_cmds = ["\n", "no page\n"]
        self.lldp_local_cmd = "show lldp info local-device\n"
        self.lldp_neighbors_cmd = "show lldp info remote-device\n"
        self.lldp_neighbors_detail_cmd = "show lldp info remote-device {0}\n"
        self.trunks_list_cmd = "show trunks\n"
        self.vlans_global_cmd = "show vlans\n"
        self.vlans_specific_cmd = "show vlans {0}\n"
        self.vms_list_cmd = None

        self.vlans_affected_to_trunks = {}

    def parse_device_from_lldp_local_info(self, result):
        device = Device()
        for line in result.splitlines():
            if not ':' in line:
                continue

            key, value = self._extract_key_and_value_from_line(line)

            self._attribute_lldp_local_info(device, key, value)

            if key == "Address":
                break

        return device

    def parse_interfaces_from_lldp_remote_info(self, result):
        interfaces = {}

        try:
            for line in result.splitlines():
                if len(line) > 57 and line[12] == '|':
                    interface = self._parse_interface_from_line(line)
                    if interface.local_port != 'LocalPort':
                        interfaces[interface.local_port] = interface
        except Exception as e:
            logging.error("Could not extract interfaces from : %s. (%s)",
                          result, e)

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
        vlans = {}
        try:
            # Here we try to find the index in between the interesting values
            # instead of using regular expressions because the output is not
            # the same on every HP switch.
            targets = ["Name", "Status"]
            name_index = None
            status_index = None
            indexes = [None]

            for line in result.splitlines():
                if all(t in line for t in targets):
                    name_index = line.find(targets[0])
                    status_index = line.find(targets[1])
                    indexes = [name_index, status_index]
                elif "----" not in line and line.strip() != "" and not \
                     self.wait_string in line and \
                     all(t is not None for t in indexes):

                    vlan_id = line[:name_index-1].strip()
                    raw_name = line[name_index:status_index-1]
                    vlan_name = raw_name.replace('|', '').strip()

                    vlans[vlan_id] = Vlan(identifier=vlan_id, name=vlan_name)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

        return vlans

    def get_vlan_detail_str(self, vlan):
        return vlan.identifier

    def associate_vlans_to_interfaces(self, interfaces, result):
        pass

    def associate_vlan_to_interfaces(self, interfaces, vlan, specific_result):
        try:
            # Here we try to find the index in between the interesting values
            # instead of using regular expressions because the output is not
            # the same on every HP switch.
            targets = ["Mode", "Unknown VLAN", "Status"]
            mode_index = None
            unknown_index = None
            status_index = None
            indexes = [None]

            for line in specific_result.splitlines():
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

                    if "Trk" in interface_id:
                        self._save_vlan_affected_to_trunk(new_vlan,
                                                          interface_id)

                    if interface_id in interfaces:
                        interfaces[interface_id].add_vlan(new_vlan)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)",
                          specific_result, e)

    def _save_vlan_affected_to_trunk(self, vlan, trunk_id):
        if trunk_id in self.vlans_affected_to_trunks:
            self.vlans_affected_to_trunks[trunk_id].append(vlan)
        else:
            self.vlans_affected_to_trunks[trunk_id] = [vlan]

    def parse_trunks(self, interfaces, trunks_result):
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
                if not match:
                    continue

                port = match.group("port").strip()
                name = match.group("name").strip()
                type = match.group("type").strip()
                group = match.group("group").strip()

                # 'group' is considered as the identifier of the trunk
                if group in trunks:
                    trunks[group].ports.append(port)
                else:
                    trunks[group] = Trunk(group=group, name=name,
                                          type=type, ports=[port])

                # Update the interface with the vlans that were previously
                # affected to the trunks.
                self._update_vlans_on_interfaces(port, group, interfaces)

        except Exception as e:
            logging.error("Could not parse trunk from : %s. (%s)",
                          trunks_result, e)

        return trunks

    def _update_vlans_on_interfaces(self, port, trunk_id, interfaces):
        if trunk_id not in self.vlans_affected_to_trunks:
            logging.warning("Warning: No vlan found for trunk %s", trunk_id)
            return

        if port in interfaces:
            for vlan in self.vlans_affected_to_trunks[trunk_id]:
                interfaces[port].add_vlan(vlan)

    def parse_vms_list(self, vm_result):
        return []

    def _attribute_lldp_remote_info(self, device, key, value):
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

    def _attribute_lldp_local_info(self, device, key, value):
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


class JuniperNetworkOutputParser(CommonSwitchParser):
    """Parses the output of Juniper switches."""
    def __init__(self):
        self.wait_string = "> "
        self.preparation_cmds = ["set cli screen-length 0\n",
                                 "set cli screen-width 0\n"]
        self.lldp_local_cmd = "show lldp local-information\n"
        self.lldp_neighbors_cmd = "show lldp neighbors\n"
        self.lldp_neighbors_detail_cmd = "show lldp neighbors interface {0}\n"
        self.trunks_list_cmd = "show lldp neighbors\n"
        self.vlans_global_cmd = "show vlans detail\n"
        self.vlans_specific_cmd = None
        self.vms_list_cmd = None

        self.trunks = {}

    def parse_device_from_lldp_local_info(self, result):
        device = Device()
        for line in result.splitlines():
            if not ':' in line:
                continue

            key, value = self._extract_key_and_value_from_line(line)

            self._attribute_lldp_local_info(device, key, value)

            if key == "Enabled":
                break

        return device

    def parse_interfaces_from_lldp_remote_info(self, result):
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
        interfaces = {}

        try:
            for line in result.splitlines():
                if len(line) <= 73:
                    continue

                local_int = line[:18].strip()
                parent_int = line[19:38].strip()
                chassis_id = line[39:58].strip().replace(':', ' ')
                port_info = line[59:71].strip()
                sys_name = line[72:].strip()

                if local_int != "Local Interface":
                    interface = Interface(local_port=local_int,
                                          remote_port=port_info,
                                          remote_mac_address=chassis_id,
                                          remote_system_name=sys_name)
                    interfaces[interface.local_port] = interface

                # Checking for trunk
                if parent_int in self.trunks:
                    self.trunks[parent_int].ports.append(local_int)
                elif parent_int != "-" and parent_int != "Parent Interface":
                    self.trunks[parent_int] = Trunk(group=parent_int,
                                                    name=parent_int,
                                                    ports=[local_int])

        except Exception as e:
            logging.error("Could not extract interfaces from : %s. (%s)",
                          result, e)

        return interfaces

    def parse_vlans(self, result):
        return {}

    def get_vlan_detail_str(self, vlan):
        return vlan.identifier

    def associate_vlans_to_interfaces(self, interfaces, result):
        """
        Example of 'show vlans detail' command:

        VLAN: vlan946, 802.1Q Tag: 946, Admin State: Enabled
          Primary IP: 192.168.84.15/24
        Number of interfaces: 3 (Active = 2)
          Tagged interfaces: ae0.0*, ge-0/0/46.0, ge-1/0/46.0*

        VLAN: vlan947, 802.1Q Tag: 947, Admin State: Enabled
        Number of interfaces: 41 (Active = 36)
          Untagged interfaces: ge-0/0/0.0*, ge-0/0/1.0*, ge-0/0/2.0*, ge-0/0/3.0*,
          ge-0/0/5.0, ge-0/0/6.0*, ge-0/0/7.0*, ge-0/0/8.0*, ge-0/0/9.0*, ge-0/0/10.0*,
          ge-0/0/11.0*, ge-0/0/12.0*, ge-0/0/13.0*, ge-0/0/14.0*, ge-0/0/15.0*,
          ge-0/0/16.0*, ge-0/0/17.0, ge-0/0/18.0*, ge-0/0/20.0*, ge-0/0/21.0*,
          ge-0/0/22.0*, ge-0/0/23.0*, ge-0/0/30.0*, ge-0/0/31.0, ge-0/0/41.0,
          ge-0/0/42.0, ge-1/0/17.0*, ge-1/0/18.0*, ge-1/0/19.0*, ge-1/0/20.0*,
          ge-1/0/21.0*, ge-1/0/22.0*, ge-1/0/23.0*, ge-1/0/24.0*, ge-1/0/25.0*,
          ge-1/0/26.0*, ge-1/0/27.0*, ge-1/0/28.0*, ge-1/0/34.0*, ge-1/0/35.0*
          Tagged interfaces: ge-1/0/46.0*

        VLAN: vlan948, 802.1Q Tag: 948, Admin State: Enabled
        Number of interfaces: 3 (Active = 3)
          Untagged interfaces: ge-0/0/4.0*, ge-0/0/19.0*
          Tagged interfaces: ge-1/0/46.0*

        {master:1}
        admin@info4200-1>
        """
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

                            if p in interfaces:
                                interfaces[p].add_vlan(vlan)

                            elif p in self.trunks: #TODO CHECK FOR TRUNKS
                                for port in self.trunks[p].ports:
                                    if port in interfaces:
                                        interfaces[port].add_vlan(vlan)

                    if "Tagged" in line:
                        vlan = Vlan()

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

    def parse_trunks(self, interfaces, trunks_result):
        return self.trunks

    def parse_vms_list(self, vm_result):
        return []

    def _attribute_lldp_remote_info(self, device, key, value):
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

    def _attribute_lldp_local_info(self, device, key, value):
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


class LinuxNetworkOutputParser(NetworkOutputParser):
    """Parses the output of Linux servers."""
    def __init__(self):
        self.wait_string = "# "
        self.preparation_cmds = []
        self.lldp_local_cmd = None
        self.lldp_neighbors_cmd = "lldpctl\n"
        self.lldp_neighbors_detail_cmd = None
        self.trunks_list_cmd = None
        self.vlans_global_cmd = "ifconfig\n"
        self.vlans_specific_cmd = "cat /sys/class/net/{0}/bonding/slaves\n"
        self.vms_list_cmd = "virsh list --all\n"

        self.trunks = {}

    def parse_device_from_lldp_local_info(self, result):
        #TODO
        return Device()

    def parse_devices_from_lldp_remote_info(self, device, lldp_summary):
        devices = []

        try:
            neighbor = Device()
            interface = Interface()

            interesting_lines = lldp_summary.splitlines()[4:] # Skip header
            for line in interesting_lines:
                if ':' in line:
                    key, value = self._extract_key_and_value_from_line(line)
                    self._attribute_lldp_remote_info(neighbor, interface, key,
                                                     value)
                elif "----" in line:
                    if interface.is_valid_lldp_interface():
                        device.interfaces[interface.local_port] = interface
                        interface = Interface()

                    devices.append(neighbor)
                    neighbor = Device()

        except Exception as e:
            logging.error("Could not extract devices from : %s. (%s)",
                          result, e)

        return devices

    def parse_interfaces_from_lldp_remote_info(self, result):
        return {}

    def parse_vlans(self, result):
        """
        This parses the output of the vlans_global_cmd command.
        """
        vlans = {}
        try:
            regex = "(?P<port>[A-z]+[0-9]*)(\.)(?P<vlan>[0-z]+)"

            for line in result.splitlines():
                match = re.search(regex, line)
                if not match:
                    continue

                port = match.group("port")
                vlan_id = match.group("vlan")

                # We need to store the port as the vlan 'name' attribute so
                # we can enter the 'associate_vlans_to_interfaces()' function
                # in order to verify if it is a bonding.
                vlans[vlan_id] = Vlan(identifier=vlan_id, name=port)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

        return vlans

    def get_vlan_detail_str(self, vlan):
        # The vlan name is the port/bonding previously set in 'parse_vlans'
        # function.
        return vlan.name

    def associate_vlans_to_interfaces(self, interfaces, result):
        pass

    def associate_vlan_to_interfaces(self, interfaces, vlan, result):
        """
        This parses the output of the vlans_specific_cmd command.
        """
        try:
            # Retrieve the port previously stored in the vlan name.
            # See 'parse_vlans' function.
            ports_affected_by_vlan = [vlan.name]
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
                    group = ports_affected_by_vlan[0]  # Old vlan "name"
                    self.trunks[group] = Trunk(group=group, ports=ports)

                    ports_affected_by_vlan = ports

                for port in ports_affected_by_vlan:
                    if port in interfaces:
                        interfaces[port].add_vlan(vlan)

        except Exception as e:
            logging.error("Could not extract vlans from : %s. (%s)", result, e)

    def parse_trunks(self, interfaces, trunks_result):
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

    def _attribute_lldp_local_info(self, device, key, value):
        raise NotImplementedError()

    def _attribute_lldp_remote_info(self, device, interface, key, value):
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
