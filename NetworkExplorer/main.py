#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Auteur : Marc-Antoine Fortier
Date   : Mars 2015
"""

import os
import sys
import time

from multiprocessing import Process, Manager, Queue

import logging
import argparse
import ConfigParser

from NetworkExplorer import *


class Configuration(object):
    pass


def _parse_args():
    parser = argparse.ArgumentParser(
        description="This program dynamically generates documentation for \
        the topology of a computing network by exploring every connected \
        switch using the LLDP protocol.")
    parser.add_argument("config", help="The configuration file.", type=str)
    parser.add_argument('--verbose', '-v', action='store_true')

    return parser.parse_args()


def _initialize_logger(logfile, verbose):
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    # Console logging handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter(" %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)

    # File logging handler
    if logfile:
        handler = logging.FileHandler(logfile, "w")
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)


def _write_results_to_file(results, outputfile):
    values = ",\n".join(value.to_JSON() for value in results.values())
    output = "[" + values + "]"

    with open(outputfile, "w") as _file:
        _file.write(output.encode('utf8'))


def main():
    args = _parse_args()

    config_file = args.config
    if not os.path.isfile(config_file):
        logging.error("Could not find configuration file '%s'.", config_file)
        exit()

    parser = ConfigParser.RawConfigParser()
    parser.read(config_file)

    conf = Configuration()

    conf.protocol = parser.get('Networkmap', 'Protocol')
    conf.source_address = parser.get('Networkmap', 'SourceAddress')
    conf.outputfile = parser.get('Networkmap', 'OutputFile')
    conf.logfile = parser.get('Networkmap', 'LogFile')

    conf.ssh_timeout = parser.getfloat('SSH', 'Timeout')
    conf.ssh_max_bytes = parser.getint('SSH', 'MaximumBytesToReceive')
    conf.ssh_max_attempts = parser.getint('SSH', 'MaximumAttempts')

    _initialize_logger(conf.logfile, args.verbose)

    queue = Queue()
    queue.put(Device(system_name=conf.source_address))

    explored_devices = Manager().dict()

    if conf.protocol != "LLDP":
        logging.error("Unsupported protocol '%s'.", conf.protocol)
        return

    start_time = time.time()

    jobs = []

    while True:
        # Starting a new process for each device added in the queue
        if not queue.empty():  # and len(jobs) < 10:
            nextDevice = queue.get()

            explorer = NetworkExplorer(device=nextDevice,
                                       parser=parser,
                                       ssh_timeout=conf.ssh_timeout,
                                       ssh_max_bytes=conf.ssh_max_bytes,
                                       ssh_max_attempts=conf.ssh_max_attempts)

            p = Process(
                target=explorer.explore_lldp,
                args=(explored_devices, queue),
                name=nextDevice.system_name)

            jobs.append(p)
            p.start()

        # Removing every process who's finished
        for j in jobs:
            if not j.is_alive():
                jobs.remove(j)

        # We're done when there aren't any process left
        if len(jobs) == 0:
            break

    if len(explored_devices) > 0:
        _write_results_to_file(explored_devices, conf.outputfile)

        logging.info("Found %s device(s) in %s second(s).",
                     len(explored_devices),
                     round(time.time() - start_time, 2))
    else:
        logging.warning("Could not find anything.")


if __name__ == "__main__":
    try:
        main()
    except ConfigParser.Error as cpe:
        logging.error("Configuration error. %s", cpe)
