#!urs/bin/env python
#encoding utf-8

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
			
	def attributeLLDPInformationToDevice(self, key, value):
		if "LocalPort" in key:
			self.remote_port = value
		elif "ChassisType" in key:
			pass # We don't need this information
		elif "ChassisId" in key:
			self.mac_address = value
		elif "PortType" in key:
			pass # We don't need this information
		elif "PortId" in key:
			self.local_port = value
		elif "SysName" in key:
			self.system_name = value
		elif "SystemDescr" in key:
			self.system_description = value
		elif "PortDescr" in key:
			pass # Do we need this information?
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
		
	def is_valid_cdp_device(self):
		#print("'{0}' == 'Switch': {1}".format(self.enabled_capabilities, self.enabled_capabilities == "Switch"))
		#print("'{0}' != 'Unsupportedformat': {1}".format(self.ip_address, self.ip_address != "Unsupportedformat"))
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
			Enabled capabilities	: {8}\n".format(
			self.mac_address,
			self.ip_address,
			self.ip_address_type,
			self.system_name,
			self.system_description,
			self.local_port,
			self.remote_port,
			self.supported_capabilities,
			self.enabled_capabilities)
		)


class NetworkDeviceBuilder(object):
	def __init__():
		pass
	
	@staticmethod
	def buildNetwordDeviceFromLLDPDetail(lldp_result):
		"""Creates NetworkDevice objects from the LLDP remote device \
		information detail of a Hewlett-Packard\xc2 switch"""
		devices = []
		currentDevice = NetworkDevice()
		
		try:
			# Parsing "show lldp info remote-device [port]" command's result
			for rawline in lldp_result.splitlines():	
				line = rawline.rstrip()
				
				if ':' in line:
					key, value = NetworkDeviceBuilder\
						.extractKeyAndValueFromLine(line)
					#print("Attributing key '{0}' and value '{1}'"
						#.format(key, value))
					currentDevice.attributeLLDPInformationToDevice(key, value)
					
				elif '#' in line:
					devices.append(currentDevice)
					currentDevice = NetworkDevice()
					
		except Exception:
			print("Could not build network devices from '{0}'."
				.format(lldp_result))
				
		return devices

	@staticmethod
	def buildNetwordDevicesFromCDPInformation(cdp_result):
		"""Creates NetworkDevice objects from the CDP neighbors detail \
		information of a Hewlett-Packard\xc2 switch"""
		devices = []
		currentDevice = NetworkDevice()
		
		try:
			# Parsing "show cdp neighbors detail" command's result
			for rawline in cdp_result.splitlines():	
				line = rawline.rstrip()
				if ':' in line:
					key, value = NetworkDeviceBuilder\
						.extractKeyAndValueFromLine(line)
					
					currentDevice.attributeCDPInformation(key, value)
				elif '-----' in line:
					devices.append(currentDevice)
					currentDevice = NetworkDevice()
		
		except Exception as e:
			print("Could not build network devices: '{0}'."
				.format(e))
	
		# Not forgetting the last device since it's not followed by a dotted line ('-----')	
		devices.append(currentDevice)
		
		switches = 0
		for device in devices:
			if device.is_valid_cdp_device():
				switches += 1
		
		print("Found {0} valid switche(s) out of {1} neighbor(s)."
			.format(switches, len(devices)))
		
		return devices
	
	@staticmethod
	def extractLocalPortsFromLLDPInformation(lldp_result):
		local_ports = []
		try:	
			# Parsing ports from "show lldp info remote-device" command's result
			for rawline in lldp_result.splitlines():	
				line = rawline.rstrip()
				if '|' in line:
					tokens = line.split()
					port = tokens[:tokens.index('|')][-1]
					
					if port != 'LocalPort' and \
						NetworkDeviceBuilder.extractSystemNameFromLine(rawline) \
						is not None:
						local_ports.append(port)		
		except Exception as e:
			print("Could not extract local ports from '{0}'."
				.format(lldp_result))
				
		return local_ports
	
	@staticmethod
	def extractSystemNameFromLine(line):
		system_name = None
		try:
			target = line[57:].replace(" ", "")
			if target != "" and "..." not in target:
				system_name = target
		except Exception as e:
			print("Could not extract system name from '{0}'."
				.format(line))
		
		return system_name

	@staticmethod
	def extractKeyAndValueFromLine(line):
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

	def explore_cdp(self, origin, devices):
		"""Recursively explores all neighbors of a Hewlett-Packard\xc2 switch 
		using the CDP protocol."""
		self._open_ssh_connection(origin.ip_address)
		
		neighbors = self._get_cdp_neighbors()
		
		self._close_ssh_connection()
		
		for neighbor in neighbors:
			if neighbor.is_valid_cdp_device() and \
				neighbor.mac_address not in devices:
				
				devices[neighbor.mac_address] = neighbor
				
				if neighbor.ip_address not in self.ignore_list:	
					print("\n{0} [{1}] ------> [{2}] {3}\n"
						.format(origin.ip_address, neighbor.remote_port,
								neighbor.local_port, neighbor.ip_address))
				
					#Let's recursively explore my neighbors' neighbors
					devices = self.explore_cdp(neighbor, devices)
		
		return devices
	
	def explore_lldp(self, origin, devices):
		"""Recursively explores all neighbors of a Hewlett-Packard\xc2 switch 
		using the LLDP protocol."""
		self._open_ssh_connection(origin.ip_address)
		
		open_ports = self._get_lldp_open_ports(origin)
		
		neighbors = self._get_lldp_neighbors(origin, open_ports)
		
		self._close_ssh_connection()
		
		for neighbor in neighbors:
			if neighbor.is_valid_lldp_device() and \
				neighbor.mac_address not in devices:
				
				devices[neighbor.mac_address] = neighbor

				if neighbor.ip_address not in self.ignore_list:
					print("\n{0} [{1}] ------> [{2}] {3}\n"
						.format(origin.ip_address, neighbor.remote_port,
								neighbor.local_port, neighbor.ip_address))
					
					#Let's recursively explore my neighbors' neighbors
					devices = self.explore_lldp(neighbor, devices)
		
		return devices
		
	def _get_lldp_open_ports(self, origin):
		command = "show lldp info remote-device\n"
		remote_devices_list = self._send_ssh_command(command, True, False)
		
		return NetworkDeviceBuilder\
				.extractLocalPortsFromLLDPInformation(remote_devices_list)
		
	def _get_lldp_neighbors(self, origin, open_ports):
		devices_details = ""
		
		for port in open_ports:
			command = "show lldp info remote-device {0}\n".format(port)
			result =  self._send_ssh_command(command, False, False)
			if result is not None:
				devices_details += result
		
		return NetworkDeviceBuilder\
				.buildNetwordDeviceFromLLDPDetail(devices_details)
	
	def _get_cdp_neighbors(self):
		command = 'show cdp neighbors detail\n'
		devices_details = self._send_ssh_command(command, True, True)
		
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
		
	def _send_ssh_command(self, command, prepare, close):
		"""Opens a SSH connection using paramiko with a Hewlett-Packard\xc2 \
		switch in order to retrieve the output data."""
		
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
		switch using the CDP protocol.")
	parser.add_argument("config", help="The configuration file.", type=str)
	return parser.parse_args()
	
if __name__ == "__main__":
	
	args = _parseargs()
	config_file = args.config
	
	if os.path.isfile(config_file):
		try:
			config.read(config_file)
				
			source_address = config.get('DEFAULT', 'SourceAddress')
			origin = NetworkDevice(ip_address = source_address, local_port = '?')
			
			protocol = config.get('DEFAULT', 'Protocol')
			
			MarcoPolo = NetworkExplorer()
			devices = {}
			
			if protocol == "LLDP":
				print("\nStarting Marco Polo's network exploration on LLDP.\n")
				MarcoPolo.explore_lldp(origin, devices)
			elif protocol == "CDP":
				print("\nStarting Marco Polo's network exploration on CDP.\n")
				MarcoPolo.explore_cdp(origin, devices)
			else:
				print("Unsupported protocol '{0}'.".format(protocol))
			
			if len(devices) > 0:
				print("\nMarco Polo found {0} devices.".format(len(devices)))
			
				for device in devices.values():
					print(str(device))
					
		except ConfigParser.Error as cpe:
			print("Configuration error. {0}".format(cpe))
	else:
		print("Could not find configuration file '{0}'.".format(config_file))


