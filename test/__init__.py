'''Unittests for scalestack.'''

import atexit
import httplib
import json
import logging
import os
import signal
import sys
import time

import gevent

import scalestack

TEST_PID = 'test.pid'
TEST_CONFIG_FILE = 'test.json'
TEST_CONFIG = json.load(open(TEST_CONFIG_FILE, 'r'))
TEST_LOG = TEST_CONFIG['scalestack']['logging']['handlers']['file']['filename']


def request(method, url, *args, **kwargs):
    '''Perform the request and handle the response.'''
    connection = httplib.HTTPConnection(TEST_CONFIG['scalestack.http']['host'],
        TEST_CONFIG['scalestack.http']['port'])
    connection.request(method, url, *args, **kwargs)
    return connection.getresponse()


def start():
    '''Fork and start the server, saving the pid in a file.'''
    kill()
    try:
        os.unlink(TEST_LOG)
    except OSError:
        pass
    pid = os.fork()
    if pid == 0:
        try:
            import coverage
            cov = coverage.coverage(data_suffix=True)
            cov.start()

            def save_coverage():
                '''Callback for signal to save coverage info to file.'''
                cov.save()

            gevent.signal(signal.SIGUSR1, save_coverage)
        except ImportError:
            pass
        core = scalestack.Core(TEST_CONFIG_FILE)
        core.force_log_level = logging.DEBUG
        core.run()
        sys.exit(0)
    pid_file = open(TEST_PID, 'w')
    pid_file.write(str(pid))
    pid_file.close()
    atexit.register(kill)
    time.sleep(1)


def kill():
    '''Try killing the server if the pid file exists.'''
    try:
        pid_file = open(TEST_PID, 'r')
        pid = pid_file.read()
        pid_file.close()
        try:
            os.kill(int(pid), signal.SIGUSR1)
            time.sleep(1)
            os.kill(int(pid), signal.SIGTERM)
            os.unlink(TEST_PID)
        except OSError:
            pass
    except IOError:
        pass

start()
