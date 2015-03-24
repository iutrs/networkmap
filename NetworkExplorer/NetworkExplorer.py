#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import os
import sys
import time
import socket

import argparse
import ConfigParser

import paramiko

from multiprocessing import Process, Manager, Queue

from NetworkDeviceBuilder import *

DEFAULT_MAX_BYTES = 2048*2048
DEFAULT_TIMEOUT = 10
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""

config = ConfigParser.RawConfigParser()


class NetworkDeviceExplorer(object):
    def __init__(self, hostname):

        self.hostname = hostname

        self.device_builder = None

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

    def explore_lldp(self, explored_devices, queue):
        """
        Explores a Hewlett-Packard\xc2 switch using the LLDP protocol in \
            order to add his valid neighbors in the queue.
        :param explored_devices: The list of the devices already explored
        :type explored_devices: NetworkDevice[]
        :param queue: The queue of the next devices to explore
        :type queue: Queue()
        """

        if self._open_ssh_connection():

            #Determining the type of the current device from the switch prompt
            switch_prompt = self._receive_ssh_output()

            self.device_builder = NetworkDeviceBuilder.get_builder_type(
                switch_prompt)

            if self.device_builder is None:
                print("Could not recognize device {0}.".format(self.hostname))
                print("Here is the switch prompt: {0}".format(switch_prompt))
                return

            #Building device from local information
            device = self._get_lldp_local_device()

            if device is None:
                print("Could not build device {0}.".format(self.hostname))
                return

            print("Discovering lldp neighbors for {0}..."
                  .format(device.system_name))

            interfaces = self._get_lldp_interfaces()
            device.interfaces = interfaces

            neighbors = self._get_lldp_neighbors(interfaces)

            self._close_ssh_connection()

            for neighbor in neighbors:
                if neighbor.is_valid_lldp_device() and \
                   neighbor.mac_address not in explored_devices:
                        explored_devices[neighbor.mac_address] = neighbor

                        if not self._ignore(neighbor.ip_address) and \
                           not self._ignore(neighbor.system_name):
                            queue.put(neighbor.system_name)

            explored_devices[device.mac_address] = device

    def _get_lldp_local_device(self):
        command = self.device_builder.lldp_local_cmd
        device_info = self._send_ssh_command(command, True)

        return self.device_builder.build_device_from_lldp_local_info(
            device_info)

    def _get_lldp_interfaces(self):
        command = self.device_builder.lldp_neighbors_cmd
        remote_devices_list = self._send_ssh_command(command, False)

        return self.device_builder.build_interfaces_from_lldp_remote_info(
            remote_devices_list)

    def _get_lldp_neighbors(self, interfaces):
        devices_details = ""

        for interface in interfaces:
            if interface.is_valid_lldp_interface():

                cmd = self.device_builder.lldp_neighbors_detail_cmd
                command = cmd.format(interface.local_port)

                result = self._send_ssh_command(command, False)
                if result is not None:
                    devices_details += result

        return self.device_builder\
            .build_devices_from_lldp_remote_info(devices_details)

    def _open_ssh_connection(self):
        success = False
        try:
            self.ssh.connect(hostname=self.hostname,
                             username=self.ssh_username,
                             password=self.ssh_password)
            self.shell = self.ssh.invoke_shell()
            self.shell.settimeout(self.ssh_timeout)
            self.shell.set_combine_stderr(True)
            time.sleep(1)
            print("Connected to {0}.".format(self.hostname))
            success = True
        except socket.error as se:
            print("Error with {0}. {1}".format(self.hostname, se))
        except paramiko.AuthenticationException as pae:
            print("Error with {0}. {1}".format(self.hostname, pae))
        except Exception as e:
            print("Unexpected error with {0}. {1}".format(self.hostname, e))

        return success

    def _close_ssh_connection(self):
        try:
            self.shell.close()
            self.ssh.close()
        except Exception as e:
            print("Could not close ssh connection with {0}. {1}"
                  .format(self.hostname, e))

    def _send_ssh_command(self, command, prepare):
        """
        Opens a SSH connection using paramiko with a Hewlett-Packard\xc2 \
        switch in order to retrieve the output data.
        :param command: The command to execute (ending by a '\\n')
        :type command: str
        :param prepare: Preparing the switch before the command
        :type prepare: bool
        :return: Returns the result from the command's output
        :rtype: str
        """
        result = None

        try:
            if prepare:
                self._prepare_switch()
                self._receive_ssh_output()

            # print("Executing command '{0}'...".format(command.rstrip()))
            self.shell.send(command)

            receive_buffer = ""

            # Waiting for the server to display all the data
            w = self.device_builder.wait_string
            while not w in receive_buffer:
                receive_buffer += self._receive_ssh_output()

            result = receive_buffer

        except socket.error as se:
            print("Socket error with {0}. {1}".format(self.hostname, se))
        except Exception as e:
            print("Unexpected error with {0}. {1}".format(self.hostname, e))

        return result

    def _prepare_switch(self):
        for cmd in self.device_builder.preparation_cmds:
            time.sleep(0.5)
            self.shell.send(cmd)

    def _receive_ssh_output(self):
        time.sleep(0.1)
        if self.shell.recv_ready:
            return self.shell.recv(self.ssh_max_bytes)

    def _ignore(self, ip_address):
        for ip in self.ignore_list:
            if ip_address and ip_address.startswith(ip):
                return True


def _parse_args():
    parser = argparse.ArgumentParser(
        description="This program dynamically generates documentation for \
        the topology of a computing network by exploring every connected \
        switch using the LLDP protocol.")
    parser.add_argument("config", help="The configuration file.", type=str)

    return parser.parse_args()


def main():
    args = _parse_args()
    config_file = args.config

    if not os.path.isfile(config_file):
        print("Could not find configuration file '{0}'.".format(config_file))
        return

    try:
        config.read(config_file)

        protocol = config.get('DEFAULT', 'Protocol')
        source_address = config.get('DEFAULT', 'SourceAddress')
        outputfile = config.get('DEFAULT', 'OutputFile')

        queue = Queue()
        queue.put(source_address)

        explored_devices = Manager().dict()

        start_time = time.time()

        if protocol == "LLDP":

            jobs = []

            while True:
                # Starting a new process for each address added in the queue
                if not queue.empty():  # and len(jobs) < 10:
                    nextAddress = queue.get()
                    p = Process(
                        target=NetworkDeviceExplorer(nextAddress).explore_lldp,
                        args=(explored_devices, queue),
                        name=nextAddress)
                    jobs.append(p)
                    p.start()

                # Removing every process who's finished
                for j in jobs:
                    if not j.is_alive():
                        jobs.remove(j)

                # We're done when there aren't any process left
                if len(jobs) == 0:
                    break

        else:
            print("Unsupported protocol '{0}'.".format(protocol))

        if len(explored_devices) > 0:
            _file = open(outputfile, "w")

            for key, device in explored_devices.items():
                _file.write("{0}\n".format(device.to_JSON()))

            _file.close()

            print("Found {0} device(s) in {1} second(s).".format(
                  len(explored_devices), round(time.time() - start_time, 2)))
        else:
            print("Could not find anything.")

    except ConfigParser.Error as cpe:
        print("Configuration error. {0}".format(cpe))

if __name__ == "__main__":
    main()
