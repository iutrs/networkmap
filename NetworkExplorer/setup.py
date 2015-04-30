#!urs/bin/env python
#encoding utf-8

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    name = 'networkmap',
    version = '0.1',
    description = 'Dynamically generate documentation for the topology of a \
        computing network by exploring every accessible equipment.',
    url = 'https://bitbucket.org/iutrsinfo/networkmap',
    author = 'Marc-Antoine Fortier',
    author_email = 'marc22fortier@hotmail.com',
    license = 'GPL',
    packages = ['network_explorer'],
    zip_safe = False)

setup(**config)
