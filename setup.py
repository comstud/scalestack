#!/usr/bin/python

import setuptools
import scalestack

setuptools.setup(
    name='scalestack',
    version=scalestack.__version__,
    description='Scale Stack',
    license='Public Domain',
    url='http://scalestack.org/',
    author='Eric Day',
    author_email='eric@livelydays.com',
    packages=['scalestack'],
    include_package_data=True,
    scripts=['bin/scalestack'],
    test_suite='nose.collector',
    install_requires=['gevent'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: No Input/Output (Daemon)',
        'License :: Public Domain',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6'])
