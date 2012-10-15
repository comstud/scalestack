#!/usr/bin/python

from setuptools import setup, find_packages
import scalestack

setup(
    name='scalestack',
    version=scalestack.__version__,
    description='Scale Stack',
    license='Public Domain',
    url='http://scalestack.org/',
    author='Eric Day',
    author_email='eric@livelydays.com',
    packages=find_packages(),
    scripts=['bin/scalestack'],
    test_suite='nose.collector',
    install_requires=['eventlet'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: No Input/Output (Daemon)',
        'License :: Public Domain',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6'])
