#!urs/bin/env python
#encoding utf-8

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    name='NetworkExplorer',
    version='0.1',
    description='Dynamically generate documentation for the topology of a \
        computing network by exploring every accessible switch.',
    url='https://bitbucket.org/iutrsinfo/networkmap',
    author='Marc-Antoine Fortier',
    author_email='marc22fortier@hotmail.com',
    license='?',
    packages=['NetworkExplorer'],
    zip_safe=False)

setup(**config)
