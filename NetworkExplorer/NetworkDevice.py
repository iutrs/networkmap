#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import json

supported_devices = ["HP", "ProCurve", "Juniper"]
supported_types = ["bridge", "Bridge"]


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

    def attribute_lldp_remote_info(self, key, value):
        raise NotImplementedError()

    def attribute_lldp_local_info(self, key, value):
        raise NotImplementedError()

    def is_valid_lldp_device(self):
        raise NotImplementedError()

    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)


class HPNetworkDevice(NetworkDevice):
    def __init__(self,
                 mac_address=None,
                 ip_address=None,
                 ip_address_type=None,
                 system_name=None,
                 system_description=None,
                 supported_capabilities=None,
                 enabled_capabilities=None):

        NetworkDevice.__init__(self,
                               mac_address,
                               ip_address,
                               ip_address_type,
                               system_name,
                               system_description,
                               supported_capabilities,
                               enabled_capabilities)

    def attribute_lldp_remote_info(self, key, value):
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
        else:
            pass

    def attribute_lldp_local_info(self, key, value):
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
        else:
            pass

    def is_valid_lldp_device(self):
        return \
            (
                self.enabled_capabilities is not None and
                any(t in self.enabled_capabilities for t in supported_types)
                and
                self.system_description is not None and
                any(d in self.system_description for d in supported_devices)
            )


class JuniperNetworkDevice(NetworkDevice):
    def __init__(self,
                 mac_address=None,
                 ip_address=None,
                 ip_address_type=None,
                 system_name=None,
                 system_description=None,
                 supported_capabilities=None,
                 enabled_capabilities=None):

        NetworkDevice.__init__(self,
                               mac_address,
                               ip_address,
                               ip_address_type,
                               system_name,
                               system_description,
                               supported_capabilities,
                               enabled_capabilities)

    def attribute_lldp_remote_info(self, key, value):
        if "Chassis ID" in key:
            self.mac_address = value.replace(':', ' ')
        elif "System name" in key:
            self.system_name = value
        elif "System Description" in key:
            self.system_description = value
        elif "Supported" in key:
            self.supported_capabilities = value
        elif "Enabled" in key:
            self.enabled_capabilities = value
        elif "Type" in key:
            self.ip_address_type = value
        elif "Address" in key:
            self.ip_address = value
        else:
            pass

    def attribute_lldp_local_info(self, key, value):
        if "Chassis ID" in key:
            self.mac_address = value.replace(':', ' ')
        elif "System name" in key:
            self.system_name = value
        elif "System descr" in key:
            self.system_description = value
        elif "Supported" in key:
            self.supported_capabilities = value
        elif "Enabled" in key:
            self.enabled_capabilities = value
#        elif "Type" in key:
#            self.ip_address_type = value
#        elif "Address" in key:
#            self.ip_address = value
        else:
            pass
            #print("Unexpected key '{0}'.".format(key))

    def is_valid_lldp_device(self):
        return \
            (
                self.enabled_capabilities is not None and
                any(t in self.enabled_capabilities for t in supported_types)
                and
                self.system_description is not None and
                any(d in self.system_description for d in supported_devices)
            )
