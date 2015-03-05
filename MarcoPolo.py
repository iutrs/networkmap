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

config = ConfigParser.RawConfigParser()

class CDPNetworkDevice(object):
	def __init__(
			self,
			port=None,
			device_id=None,
			address_type=None,
			address=None,
			platform=None,
			capability=None,
			device_port=None,
			version=None):
		
		self.port = port
		self.device_id = device_id
		self.address_type = address_type
		self.address = address
		self.platform = platform
		self.capability = capability
		self.device_port = device_port
		self.version = version

	@staticmethod
	def buildNetwordDevicesFrom(cdp_result):
		"""Creates CDPNetworkDevice objects from the CDP neighbors detail \
		information of a Hewlett-Packard\xc2 switch"""
		devices = []
		currentDevice = CDPNetworkDevice()
		
		if cdp_result is None:
			print("Could not build network devices from '{0}'."
				.format(output_file))
				
		# Parsing cdp neighbors information/detail
		for rawline in cdp_result.splitlines():	
			try:
				line = rawline.rstrip()
				if ':' in line:
					tokens = line.split()
					key = [' '.join(tokens[:tokens.index(':')])][0]
					value = [' '.join(tokens[tokens.index(':')+1:])][0]

					CDPNetworkDevice.attributeToDevice(currentDevice, key, value)
			
				elif '-----' in line:
					devices.append(currentDevice)
					currentDevice = CDPNetworkDevice()
			except Exception:
				print("There was a problem parsing the cdp neighbors information.")
				pass
	
		# Not forgetting the last device since it's not followed by a dotted line ('-----')	
		devices.append(currentDevice)
		
		switches = 0
		for device in devices:
			if CDPNetworkDevice.is_valid_device(device):
				switches += 1
		
		print("Found {0} valid switche(s) out of {1} neighbor(s)."
			.format(switches, len(devices)))
		
		return devices
		
	@staticmethod
	def attributeToDevice(device, key, value):
		if "Device ID" in key:
			device.device_id = value
		elif "Device Port" in key:
			device.device_port = value
		elif "Port" in key:
			device.port = value
		elif "Address Type" in key:
			device.address_type = value
		elif "Address" in key:
			device.address = value
		elif "Platform" in key:
			device.platform = value
		elif "Capability" in key:
			device.capability = value
		elif "Version" in key:
			device.version = value
		else:
			print("Unexpected key '{0}'.".format(key))
	
	@staticmethod	
	def is_valid_device(device):
		valid = \
		(
			device.capability == "Switch" and \
			device.address != "Unsupported format"
		)
		return valid


class NetworkExplorer(object):
	def __init__(self):
		pass
	
	def explore(self, origin, devices):
		"""Recursively explores all cdp neighbors switches of a \
		Hewlett-Packard\xc2 switch."""
		command = 'show cdp neighbors detail\n'
		raw_result = self._send_ssh_command(origin.address, command)
		
		if raw_result is not None:
			neighbors = CDPNetworkDevice.buildNetwordDevicesFrom(raw_result)
		
			for neighbor in neighbors:	
				if CDPNetworkDevice.is_valid_device(neighbor) and \
					neighbor.device_id not in devices:
					
					devices[neighbor.device_id] = neighbor
							
					print("\n{0} [{1}] ------> [{2}] {3}\n"
					.format(origin.address, origin.port,
							neighbor.port, neighbor.address))
					
					#Recursive fun starts here!
					devices = self.explore(neighbor, devices)
		
		return devices
		
	def _send_ssh_command(self, hostname, command):
		"""Opens a SSH connection using paramiko with a Hewlett-Packard\xc2 \
		switch in order to retrieve the output data."""
		
		ssh = paramiko.SSHClient()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		
		ssh_timeout = DEFAULT_TIMEOUT
		ssh_max_bytes = DEFAULT_MAX_BYTES
		
		try:
			print("Connecting to {0}...".format(hostname))
			
			ssh_timeout = config.getfloat('SSH', 'Timeout')
			ssh_max_bytes = config.getint('SSH', 'MaximumBytesToReceive')
			
			ssh_username = config.get('SSH', 'Username')
			ssh_password = config.get('SSH', 'Password')
			
			ssh.connect(hostname, username=ssh_username, password=ssh_password)
				
		except socket.error as se:
			print("Socket error: {0}".format(se))
			return None
		except paramiko.AuthenticationException as pae:
			print("Authentication error: {0}".format(pae))
			return None
		except ConfigParser.Error as cpe:
			print("Configuration error: {0}".format(cpe))
			return None
		except Exception as e:
			print("Unexpected error: {0}".format(e))
			return None
				
		print("Connected to {0}.".format(hostname))
		
		shell = ssh.invoke_shell()
		shell.settimeout(ssh_timeout)

		# These 'time.sleep()' are used to give enough time for the switch to operate
		
		try:
			print("Preparing command...")
			time.sleep(1)
			shell.send('\n') # Bypassing the HP switch welcome page
			time.sleep(2)
			shell.send('no page\n') # Asking the switch to display all data at once
			time.sleep(1)
		
			shell.recv(ssh_max_bytes) # Flushing useless data
		
			print("Executing command...")
		
			shell.send(command)
			time.sleep(5) # Waiting for the server to display all the data
			# TODO Change for a while loop until we've got everything		
			result = shell.recv(ssh_max_bytes)

			shell.close()
			ssh.close()
			print("Closed connection to {0}.".format(hostname))
			
		except socket.timeout as st:
			print("Socket error: {0}".format(st))
			return None
		
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
			origin = CDPNetworkDevice(address = source_address, port = '?')

			MarcoPolo = NetworkExplorer()
			devices = {}
		
			print("\nStarting Marco Polo's network exploration.\n")
			MarcoPolo.explore(origin, devices)
	
			print("\nMarco Polo found {0} devices.".format(len(devices)))
			
		except ConfigParser.Error as cpe:
			print("Configuration error. {0}".format(cpe))
	else:
		print("Could not find configuration file '{0}'.".format(config_file))


