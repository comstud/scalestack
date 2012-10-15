'''Unittests for scalestack.'''

import atexit
import httplib
import logging
import os
import signal
import shutil
import sys
import time

import scalestack

TEST_HOST = '127.0.0.1'
TEST_PORT = 8123
TEST_PATH = 'test.data'
TEST_PID = '%s/pid' % TEST_PATH
TEST_LOGGING = scalestack.DEFAULT_LOGGING
TEST_LOGGING['handlers']['file'] = {
    'class': 'logging.FileHandler',
    'filename': '%s/log' % TEST_PATH,
    'formatter': 'default'}
TEST_LOGGING['root']['handlers'] = ['file']


def request(method, url, *args, **kwargs):
    '''Perform the request and handle the response.'''
    connection = httplib.HTTPConnection(TEST_HOST, TEST_PORT)
    connection.request(method, url, *args, **kwargs)
    return connection.getresponse()


def start():
    '''Fork and start the server, saving the pid in a file.'''
    if os.path.exists(TEST_PATH):
        shutil.rmtree(TEST_PATH)
    os.mkdir(TEST_PATH)
    kill()
    pid = os.fork()
    if pid == 0:
        try:
            import coverage
            cov = coverage.coverage(data_suffix=True)
            cov.start()

            def save_coverage(_signum, _frame):
                '''Callback for signal to save coverage info to file.'''
                cov.save()

            signal.signal(signal.SIGUSR1, save_coverage)
        except ImportError:
            pass
        core = scalestack.Core(TEST_PATH)
        core.force_log_level = logging.DEBUG
        core.config_set('http', {'host': TEST_HOST, 'port': TEST_PORT})
        core.config_set('logging', TEST_LOGGING)
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
        except OSError:
            pass
    except IOError:
        pass

start()
