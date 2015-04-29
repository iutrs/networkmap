# -*- coding: utf-8 -*-
import ConfigParser
import fnmatch
import os

import paramiko


class NoAuthRequested(Exception):
    pass


class AuthConfigError(Exception):
    pass


class AuthManager(object):
    def __init__(self, parser):
        """
        parser: ConfigParser.RawConfigParser instance
                which contains the [Auth] sections
        """
        self._parser = parser

    def _get_options(self, auth_section):
        """
        Given a specific section name, returns a kwargs dict
        which can directly be used in the paramiko.SSHClient.connect
        method
        """
        options = dict(self._parser.items(auth_section))
        if set(options) != set(["username", "password"]) and \
            set(options) != set(["key", "username"]) and \
            set(options) != set(["key", "username", "password"]):

            raise AuthConfigError("Invalid auth section %s" % auth_section)

        if "key" in options:
            path = options.pop("key")
            path = os.path.expanduser(path)
            pkey = paramiko.RSAKey.from_private_key_file(path)
            options["pkey"] = pkey

        return options

    def get_params(self, hostname, device_type):
        # Find by hostname
        for pattern, section_name in self._parser.items("Auth"):
            # Option names are lowercased by the parser
            # fnmatch.fnmatch() is case-sensitive
            hostname = hostname.lower()
            if fnmatch.fnmatch(hostname, pattern):
                if section_name == "":
                    raise NoAuthRequested("No auth requested for %s" % hostname)

                full_section_name = "Auth.%s" % section_name
                try:
                    return self._get_options(full_section_name)
                except ConfigParser.NoSectionError:
                    raise AuthConfigError(
                        "Auth section %s does not exist" % section_name)

        # Find by device, or fallback to defaults if defined
        full_section_name = "Auth.%s" % device_type
        for attempt in (full_section_name, "Auth.default"):
            try:
                return self._get_options(full_section_name)
            except ConfigParser.NoSectionError:
                continue

        raise AuthConfigError(
            "No Auth method provided for host {} ({})".format(
            hostname, device_type))


import unittest
import StringIO


class AuthManagerTester(unittest.TestCase):
    def setUp(self):
        example = """
[Auth]
hostname_noauth =
HOSTNAME_CUSTOM = hostname_custom
hostname_unknownopt = hostname_unknownopt
hostname_missingsection = hostname_missingsection
mygroup* = mygroup

[Auth.hostname_custom]
username = admin_hostname_custom
password = password_hostname_custom

[Auth.hostname_unknownopt]
username = admin_hostname_unknownopt
password = password_hostname_unknownopt
UnknownOption = foo

[Auth.mygroup]
username = admin_mygroup
password = password_mygroup

[Auth.linux]
key = /tmp/test-key
username = root

[Auth.hp]
username = admin_hp
password = password_hp

[Auth.juniper]
username = admin_juniper
"""

        example = StringIO.StringIO(example)
        parser = ConfigParser.RawConfigParser()
        parser.readfp(example)

        self.auth_manager = AuthManager(parser)

    def test_by_plain_name_no_auth(self):
        with self.assertRaises(NoAuthRequested):
            params = self.auth_manager.get_params(
                "hostname_noauth", "hp")

    def test_by_plain_name(self):
        params = self.auth_manager.get_params(
            "HOSTNAME_CUSTOM", "hp")
        expected = {
            "username": "admin_hostname_custom",
            "password": "password_hostname_custom"}
        self.assertEqual(params, expected)

    def test_by_glob(self):
        params = self.auth_manager.get_params(
            "mygroup123", "hp")
        expected = {
            "username": "admin_mygroup",
            "password": "password_mygroup"}
        self.assertEqual(params, expected)

    def test_by_type_and_password(self):
        params = self.auth_manager.get_params(
            "unknown", "hp")
        expected = {
            "username": "admin_hp",
            "password": "password_hp"}
        self.assertEqual(params, expected)

    def test_by_type_and_key(self):
        k = paramiko.RSAKey.generate(1024)
        k.write_private_key_file("/tmp/test-key")
        with open("/tmp/test-key.pub", "w") as pub:
            pub.write(k.get_base64())
        params = self.auth_manager.get_params(
            "unknown", "linux")
        expected = {
            "pkey": paramiko.RSAKey.from_private_key_file("/tmp/test-key"),
            "username": "root"}
        self.assertEqual(params, expected)
        os.unlink("/tmp/test-key")
        os.unlink("/tmp/test-key.pub")

    def test_username_without_password(self):
        with self.assertRaises(AuthConfigError):
            params = self.auth_manager.get_params(
                "unknown", "juniper")

    def test_unknown_option(self):
        with self.assertRaises(AuthConfigError):
            params = self.auth_manager.get_params(
                "hostname_unknownopt", "juniper")

    def test_missing_section(self):
        with self.assertRaises(AuthConfigError):
            params = self.auth_manager.get_params(
                "hostname_missingsection", "juniper")

    def test_missing_type(self):
        with self.assertRaises(AuthConfigError):
            params = self.auth_manager.get_params(
                "unknown", "unknown")


if __name__ == "__main__":
    unittest.main()
