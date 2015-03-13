#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur	: Marc-Antoine Fortier
Date	: Mars 2015
"""

import os
import sys
import time
import socket

import argparse
import ConfigParser

import paramiko
import json

DEFAULT_MAX_BYTES = 2048*2048
DEFAULT_TIMEOUT = 10
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""

config = ConfigParser.RawConfigParser()

class NetworkDevice(object):
	def __init__(
			self,
			mac_address=None,
			ip_address=None,
			ip_address_type=None,
			system_name=None,
			system_description=None,
			local_port=None,
			remote_port=None,
			supported_capabilities=None,
			enabled_capabilities=None):
		
		self.mac_address = mac_address
		self.ip_address = ip_address
		self.ip_address_type = ip_address_type
		self.system_name = system_name
		self.system_description = system_description
		self.local_port = local_port
		self.remote_port = remote_port
		self.supported_capabilities = supported_capabilities
		self.enabled_capabilities = enabled_capabilities
		self.children = []
		
	def attributeCDPInformation(self, key, value):
		if "DeviceID" in key:
			self.mac_address = value
		elif "DevicePort" in key:
			self.local_port = value
		elif "Port" in key:
			self.remote_port = value
		elif "AddressType" in key:
			self.ip_address_type = value
		elif "Address" in key:
			self.ip_address = value
		elif "Platform" in key:
			self.system_description = value
		elif "Capability" in key:
			self.enabled_capabilities = value
		elif "Version" in key:
			pass # This attribute is the same as 'Platform'
		else:
			print("Unexpected key '{0}'.".format(key))
			
	def attributeLLDPRemoteInformation(self, key, value):
		if "LocalPort" in key:
			self.remote_port = value
		elif "ChassisType" in key:
			pass # Do we need this information?
		elif "ChassisId" in key:
			self.mac_address = value
		elif "PortType" in key:
			pass # Do we need this information?
		elif "PortId" in key:
			pass # Do we need this information?
		elif "SysName" in key:
			self.system_name = value
		elif "SystemDescr" in key:
			self.system_description = value
		elif "PortDescr" in key:
			self.local_port = value
		elif "Pvid" in key:
			pass # Often empty information
		elif "SystemCapabilitiesSupported" in key:
			self.supported_capabilities = value
		elif "SystemCapabilitiesEnabled" in key:
			self.enabled_capabilities = value
		elif "Type" in key:
			self.ip_address_type = value
		elif "Address" in key:
			self.ip_address = value
		elif "EndpointClass" in key:
			pass # Useless information
		else:
			print("Unexpected key '{0}'.".format(key))
			
	def attributeLLDPLocalInformation(self, key, value):
		if "ChassisType" in key:
			pass # Do we need this information?
		elif "ChassisId" in key:
			self.mac_address = value
		elif "SystemName" in key:
			self.system_name = value
		elif "SystemDescription" in key:
			self.system_description = value
		elif "SystemCapabilitiesSupported" in key:
			self.supported_capabilities = value
		elif "SystemCapabilitiesEnabled" in key:
			self.enabled_capabilities = value
		elif "ManagementAddress" in key:
			pass # Useless information
		elif "Type" in key:
			self.ip_address_type = value
		elif "Address" in key:
			self.ip_address = value
		else:
			print("Unexpected key '{0}'.".format(key))
		
	def is_valid_cdp_device(self):
		return \
		(
			self.enabled_capabilities == "Switch" and \
			self.ip_address != "Unsupportedformat"
		)
		
	def is_valid_lldp_device(self):
		return \
		(
			"Switch" in self.system_description and \
			self.ip_address is not None
		)
		
	def __str__(self):
		return \
		(
			"\
			MAC			: {0}\n \
			IP Address		: {1}\n \
			IP Address type		: {2}\n \
			Name			: {3}\n \
			Description		: {4}\n \
			Local port		: {5}\n \
			Remote port		: {6}\n \
			Supported capabilities	: {7}\n \
			Enabled capabilities	: {8}\n \
			Children		: {9}\n".format(
			self.mac_address,
			self.ip_address,
			self.ip_address_type,
			self.system_name,
			self.system_description,
			self.local_port,
			self.remote_port,
			self.supported_capabilities,
			self.enabled_capabilities,
			len(self.children))
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
		
		:param lldp_result: The result of the command "show lldp info remote-device [port]"
		:type lldp_result: string
		:return: An array of the NetworkDevice objects built from the provided result
		:rtype: NetworkDevice[]
		"""
		devices = []
		
		try:
			currentDevice = NetworkDevice()
			
			for rawline in lldp_result.splitlines():
				if ':' in rawline:
					key, value = NetworkDeviceBuilder\
						._extractKeyAndValueFromLine(rawline)
						
					currentDevice.attributeLLDPRemoteInformation(key, value)
					
				elif '#' in rawline:
					devices.append(currentDevice)
					currentDevice = NetworkDevice()
					
		except Exception:
			print("Could not build network devices from '{0}'."
				.format(lldp_result))
				
		return devices
		
	@staticmethod
	def buildNetwordDeviceFromLLDPLocalInformation(lldp_result):
		"""
		Builds a NetworkDevice object from the LLDP local device \
		information detail of a Hewlett-Packard\xc2 switch.
		
		:param lldp_result: The result of the command "show lldp info local-device"
		:type lldp_result: string
		:return: The NetworkDevice object built from the provided result
		:rtype: NetworkDevice
		"""
		device = NetworkDevice()
		
		try:
			for rawline in lldp_result.splitlines():	
				if ':' in rawline:
					key, value = NetworkDeviceBuilder\
						._extractKeyAndValueFromLine(rawline)
						
					device.attributeLLDPLocalInformation(key, value)
				
		except Exception:
			print("Could not build network device from '{0}'."
				.format(lldp_result))
				
		return device
		
	@staticmethod
	def buildNetwordDevicesFromCDPInformation(cdp_result):
		"""
		Builds an array of NetworkDevice objects from the CDP neighbors detail \
		information of a Hewlett-Packard\xc2 switch.
		
		:param cdp_result: The result of the command "show cdp neighbors detail"
		:type cdp_result: string
		:return: An array of the NetworkDevice objects built from the provided result
		:rtype: NetworkDevice[]
		"""
		devices = []
		
		try:
			currentDevice = NetworkDevice()
			
			for rawline in cdp_result.splitlines():	
				line = rawline.rstrip()
				if ':' in line:
					key, value = NetworkDeviceBuilder\
						._extractKeyAndValueFromLine(line)
					#print("Attributing key '{0}' and value '{1}'"
					#	.format(key, value))
					currentDevice.attributeCDPInformation(key, value)
				elif '-----' in line:
					devices.append(currentDevice)
					currentDevice = NetworkDevice()
				
			# Not forgetting the last device since it's not followed by a dotted line ('-----')
			devices.append(currentDevice)
			
		except Exception as e:
			print("Could not build network devices: '{0}'."
				.format(e))
				
		return devices
	
	@staticmethod
	def extractLocalPortsFromLLDPRemoteInformation(lldp_result):
		"""
		Builds an array containing the connected LLDP ports of a Hewlett-Packard\xc2 switch.
		
		:param lldp_result: The result of the command "show lldp info remote-device"
		:type lldp_result: string
		:return: An array of the of the connected ports built from the provided result
		:rtype: str[]
		"""
		local_ports = []
		
		try:
			for rawline in lldp_result.splitlines():	
				if '|' in rawline:
					tokens = rawline.split()
					port = tokens[:tokens.index('|')][-1]
					
					if port != 'LocalPort' and NetworkDeviceBuilder\
						._extractSystemNameFromLine(rawline) is not None:
						
						local_ports.append(port)
		except Exception as e:
			print("Could not extract local ports from '{0}'."
				.format(lldp_result))
				
		return local_ports
	
	@staticmethod
	def _extractSystemNameFromLine(line):
		system_name = None
		try:
			target = line[57:].replace(" ", "")
			if target != "" and "..." not in target:
				system_name = target
		except Exception as e:
			print("Could not extract system name from '{0}'.".format(line))
		
		return system_name
	
	@staticmethod
	def _extractKeyAndValueFromLine(line):
		tokens = line.split(':')
		key = tokens[0].replace(" ", "")
		value = tokens[1].replace(" ", "")
		
		return (key, value)


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
	
	def explore_cdp(self, origin, explored_devices):
		"""
		Recursively explores all neighbors of a Hewlett-Packard\xc2 switch 
		using the CDP protocol.
		
		:param origin: The NetworkDevice starting point"
		:type origin: NetworkDevice
		:param explored_devices: The list of the mac addresses already explored
		:type origin: str[]
		:return: Returns the origin and the list of explored devices
		:rtype: NetworkDevice, str[]
		"""
		self._open_ssh_connection(origin.ip_address)
		
		if not explored_devices:
			#TODO Find a way not to use LLDP!
			origin = self._get_lldp_local_device(origin)
			explored_devices.append(origin.mac_address)
			
		neighbors = self._get_cdp_remote_devices()
		
		self._close_ssh_connection()
		
		for neighbor in neighbors:
			if neighbor.is_valid_cdp_device() and \
				neighbor.mac_address not in explored_devices:
				
				explored_devices.append(neighbor.mac_address)
				
				origin.children.append(neighbor)
				
				if neighbor.ip_address not in self.ignore_list:
					print("\n{0} [{1}] ------> [{2}] {3}\n"
						.format(origin.ip_address, neighbor.remote_port,
								neighbor.local_port, neighbor.ip_address))
								
					#Let's recursively explore my neighbors' neighbors
					_trash, explored_devices = \
						self.explore_cdp(neighbor, explored_devices)
		
		return origin, explored_devices
	
	def explore_lldp(self, origin, explored_devices):
		"""
		Recursively explores all neighbors of a Hewlett-Packard\xc2 switch 
		using the LLDP protocol.
		
		:param origin: The NetworkDevice starting point"
		:type origin: NetworkDevice
		:param explored_devices: The list of the mac addresses already explored
		:type origin: str[]
		:return: Returns the origin and the list of explored devices
		:rtype: NetworkDevice, str[]
		"""
		self._open_ssh_connection(origin.ip_address)
		
		if not explored_devices:
			origin = self._get_lldp_local_device(origin)
			explored_devices.append(origin.mac_address)
			
		open_ports = self._get_lldp_open_ports(origin)
		
		neighbors = self._get_lldp_remote_devices(origin, open_ports)
		
		self._close_ssh_connection()
		
		for neighbor in neighbors:
			if neighbor.is_valid_lldp_device() and \
				neighbor.mac_address not in explored_devices:
				
				explored_devices.append(neighbor.mac_address)
				
				origin.children.append(neighbor)
				
				if neighbor.ip_address not in self.ignore_list:
					print("\n{0} [{1}] ------> [{2}] {3}\n"
						.format(origin.system_name, neighbor.remote_port,
								neighbor.local_port, neighbor.system_name))
					
					#Let's recursively explore my neighbors' neighbors
					_trash, explored_devices = \
						self.explore_lldp(neighbor, explored_devices)
					
		return origin, explored_devices
		
	def _get_lldp_local_device(self, origin):
		command = "show lldp info local-device\n"
		device_info = self._send_ssh_command(command, True)
		
		return NetworkDeviceBuilder\
				.buildNetwordDeviceFromLLDPLocalInformation(device_info)
	
	def _get_lldp_open_ports(self, origin):
		command = "show lldp info remote-device\n"
		remote_devices_list = self._send_ssh_command(command, True)
		
		return NetworkDeviceBuilder\
				.extractLocalPortsFromLLDPRemoteInformation(remote_devices_list)
	
	def _get_lldp_remote_devices(self, origin, open_ports):
		devices_details = ""
		for port in open_ports:
			command = "show lldp info remote-device {0}\n".format(port)
			result =  self._send_ssh_command(command, False)
			if result is not None:
				devices_details += result
				
		return NetworkDeviceBuilder\
				.buildNetwordDevicesFromLLDPRemoteInformation(devices_details)
	
	def _get_cdp_remote_devices(self):
		command = 'show cdp neighbors detail\n'
		devices_details = self._send_ssh_command(command, True)
		
		return NetworkDeviceBuilder\
				.buildNetwordDevicesFromCDPInformation(devices_details)
	
	def _open_ssh_connection(self, hostname):
		try:
			print("Connecting to {0}...".format(hostname))
			self.ssh.connect(hostname,
				username=self.ssh_username,
				password=self.ssh_password)
				
			self.shell = self.ssh.invoke_shell()
			self.shell.settimeout(self.ssh_timeout)
			print("Connected to {0}.".format(hostname))
		except socket.error as se:
			print("Socket error: {0}".format(se))
		except paramiko.AuthenticationException as pae:
			print("Authentication error: {0}".format(pae))
		except Exception as e:
			print("Unexpected error: {0}".format(e))
	
	def _close_ssh_connection(self):
		try:
			self.shell.close()
			self.ssh.close()
			print("Successfully closed ssh connection.")
		except Exception:
			print("Could not close ssh connection.")
	
	def _send_ssh_command(self, command, prepare):
		"""
		Opens a SSH connection using paramiko with a Hewlett-Packard\xc2 \
		switch in order to retrieve the output data.
		
		:param command: The command to execute on the device (ending by a '\\n')
		:type command: str
		:param prepare: Preparing the switch before the command
		:type prepare: bool
		:return: Returns the result from the command's output
		:rtype: str
		"""
		result = None
		
		try:
			# These 'time.sleep()' are used to give enough time for the switch to operate
			if prepare:
				print("Preparing command...")
				time.sleep(1)
				self.shell.send('\n') # Bypassing the HP switch welcome page
				time.sleep(2)
				self.shell.send('no page\n') # Asking the switch to display all data at once
				time.sleep(1)
				
				self.shell.recv(self.ssh_max_bytes) # Flushing useless data
			
			print("Executing command '{0}'...".format(command.rstrip()))
			self.shell.send(command)
			
			# TODO Change for a while loop until we've got everything
			time.sleep(3) # Waiting for the server to display all the data
			
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
		switch using the LLDP or CDP protocol.")
	parser.add_argument("config", help="The configuration file.", type=str)
	
	return parser.parse_args()

def main():
	args = _parseargs()
	config_file = args.config
	
	if os.path.isfile(config_file):
		try:
			config.read(config_file)
			
			outputfile = config.get('DEFAULT', 'OutputFile')
			
			source_address = config.get('DEFAULT', 'SourceAddress')
			origin = NetworkDevice(ip_address = source_address)
			
			protocol = config.get('DEFAULT', 'Protocol')
			
			MarcoPolo = NetworkExplorer()
			devices = []
			
			if protocol == "LLDP":
				print("\nStarting Marco Polo's network exploration on LLDP.\n")
				origin, devices = MarcoPolo.explore_lldp(origin, devices)
			elif protocol == "CDP":
				print("\nStarting Marco Polo's network exploration on CDP.\n")
				origin, devices = MarcoPolo.explore_cdp(origin, devices)
			else:
				print("Unsupported protocol '{0}'.".format(protocol))
				
			if len(devices) > 0:
				print("\nMarco Polo found {0} devices:".format(len(devices)))
				print(origin.to_JSON())
				
				_file = open(outputfile, "w")
				_file.write(origin.to_JSON())
				_file.close()
			else:
				print("\nMarco Polo could not find anything.")
				
		except ConfigParser.Error as cpe:
			print("Configuration error. {0}".format(cpe))
		except Exception as e:
			print("Unexpected error. {0}".format(e))
	else:
		print("Could not find configuration file '{0}'.".format(config_file))

if __name__ == "__main__":
	main()
	
	
