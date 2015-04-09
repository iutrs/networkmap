#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import json

supported_devices = ["HP", "ProCurve", "Juniper", "Debian", "Linux"]
supported_types = ["bridge", "Bridge"]


class VlanMode():
    TRUNK = "Tagged"
    ACCESS = "Untagged"


class VlanStatus():
    ACTIVE = "Up"
    INACTIVE = "Down"


class Vlan(object):
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

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class VirtualMachine(object):
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

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class NetworkDeviceInterface(object):
    def __init__(
            self,
            local_port=None,
            remote_port=None,
            remote_mac_address=None,
            remote_system_name=None,
            vlans=[]):

        self.local_port = local_port
        self.remote_port = remote_port
        self.remote_mac_address = remote_mac_address
        self.remote_system_name = remote_system_name
        self.vlans = vlans

    def is_valid_lldp_interface(self):
        return \
            (
                self.remote_system_name is not None and
                self.remote_system_name != ""
            )

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class NetworkDevice(object):
    def __init__(
            self,
            mac_address=None,
            ip_address=None,
            ip_address_type=None,
            system_name=None,
            system_description=None,
            supported_capabilities="",
            enabled_capabilities="",
            interfaces=[],
            virtual_machines=[]):

        self.mac_address = mac_address
        self.ip_address = ip_address
        self.ip_address_type = ip_address_type
        self.system_name = system_name
        self.system_description = system_description
        self.supported_capabilities = supported_capabilities
        self.enabled_capabilities = enabled_capabilities
        self.interfaces = interfaces
        self.virtual_machines = virtual_machines

    def is_valid_lldp_device(self):
        return \
            (
                self.enabled_capabilities is not None and
                any(t in self.enabled_capabilities for t in supported_types)
                and
                self.system_description is not None and
                any(d in self.system_description for d in supported_devices)
            )

    def is_linux_server(self):
        return \
            (
                self.system_description is not None and
                any(d in self.system_description for d in ["Linux", "Debian",
                                                           "Ubuntu"])
            )

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)
