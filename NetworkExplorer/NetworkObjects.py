#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import json

HP_DEVICES = ["HP", "Hewlett-Packard", "ProCurve"]
JUNIPER_DEVICES = ["Juniper", "JUNOS"]
LINUX_DEVICES = ["Linux", "Debian", "Ubuntu"]

SUPPORTED_DEVICES = HP_DEVICES + JUNIPER_DEVICES + LINUX_DEVICES
SUPPORTED_TYPES = ["bridge", "Bridge"]


class VlanMode():
    TRUNK = "Tagged"
    ACCESS = "Untagged"


class VlanStatus():
    ACTIVE = "Up"
    INACTIVE = "Down"


class NetworkObject(object):
    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class Vlan(NetworkObject):
    def __init__(
            self,
            identifier=None,
            name=None,
            mode=None,
            status=None):

        self.identifier = identifier
        self.name = name
        self.mode = mode
        self.status = status


class VirtualMachine(NetworkObject):
    def __init__(
            self,
            identifier=None,
            name=None,
            state=None):

        self.identifier = identifier
        self.name = name
        self.state = state

    def is_valid(self):
        return \
            (
                all(a is not None for a in [self.identifier, self.name,
                                            self.state]) and
                self.identifier != "-" and self.identifier != ""
            )


class Trunk(NetworkObject):
    def __init__(
            self,
            name=None,
            type=None,
            group=None,
            ports=None):

        self.name = name
        self.type = type
        self.group = group
        self.ports = ports or []


class Interface(NetworkObject):
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
        self.vlans = vlans or {}

    def add_vlan(self, vlan):
        if not vlan.identifier in self.vlans:
            self.vlans[vlan.identifier] = vlan

    def is_valid_lldp_interface(self):
        return \
            (
                self.remote_system_name is not None and
                self.remote_system_name != ""
            )


class Device(NetworkObject):
    def __init__(
            self,
            mac_address=None,
            ip_address=None,
            ip_address_type=None,
            system_name=None,
            system_description=None,
            supported_capabilities=None,
            enabled_capabilities=None,
            interfaces=None,
            trunks=None,
            virtual_machines=None):

        self.mac_address = mac_address
        self.ip_address = ip_address
        self.ip_address_type = ip_address_type
        self.system_name = system_name
        self.system_description = system_description
        self.supported_capabilities = supported_capabilities or ""
        self.enabled_capabilities = enabled_capabilities or ""
        self.interfaces = interfaces or []
        self.trunks = trunks or {}
        self.virtual_machines = virtual_machines or []

    def is_valid_lldp_device(self):
        return \
            (
                self.enabled_capabilities is not None and
                any(t in self.enabled_capabilities for t in SUPPORTED_TYPES)
                and
                self.system_description is not None and
                any(d in self.system_description for d in SUPPORTED_DEVICES)
            )

    def is_linux_server(self):
        return \
            (
                self.system_description is not None and
                any(d in self.system_description for d in LINUX_DEVICES)
            )
