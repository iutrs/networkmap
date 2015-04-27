# -*- coding: utf-8 -*-
import fnmatch
import os
import ConfigParser

import paramiko


class AuthConfigError(Exception):
    pass


class AuthManager(object):
    def __init__(self, parser):
        """
        parser: ConfigParser.RawConfigParser instance
        """
        self._parser = parser

    def _get_options(self, auth_section):
        options = dict(self._parser.items(auth_section))
        if set(options) == set(["username", "password"]) or \
            set(options) == set(["key"]):

            if "key" in options:
                path = options.pop("key")
                path = os.path.expanduser(path)
                pkey = paramiko.RSAKey.from_private_key_file(path)
                options["pkey"] = pkey
            return options
        else:
            raise AuthConfigError("Invalid auth section %s" % auth_section)

    def get_params(self, hostname, device_type):
        # Find by hostname
        for pattern, section_name in self._parser.items("Auth"):
            if fnmatch.fnmatch(hostname, pattern):
                if section_name == "":
                    return None
                else:
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
hostname_custom = hostname_custom
hostname_unknownopt = hostname_unknownopt
hostname_missingsection = hostname_missingsection
mygroup* = mygroup

[Auth.hostname_custom]
Username = admin_hostname_custom
Password = password_hostname_custom

[Auth.hostname_unknownopt]
Username = admin_hostname_unknownopt
Password = password_hostname_unknownopt
UnknownOption = foo

[Auth.mygroup]
Username = admin_mygroup
Password = password_mygroup

[Auth.linux]
Key = ~/key.linux

[Auth.hp]
Username = admin_hp
Password = password_hp

[Auth.juniper]
Username = admin_juniper
"""

        example = StringIO.StringIO(example)
        parser = ConfigParser.RawConfigParser()
        parser.readfp(example)

        self.auth_manager = AuthManager(parser)

    def test_by_plain_name_no_auth(self):
        params = self.auth_manager.get_params(
            "hostname_noauth", "hp")
        self.assertEqual(params, None)

    def test_by_plain_name(self):
        params = self.auth_manager.get_params(
            "hostname_custom", "hp")
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
        params = self.auth_manager.get_params(
            "unknown", "linux")
        expected = {
            "pkey": os.path.expanduser("~/key.linux")}
        self.assertEqual(params, expected)

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
