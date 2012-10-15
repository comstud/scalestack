'''Core variables, classes and functions for the scalestack package. Also
handle option parsing and starting the core when run from the command line.'''

import gettext
import json
import logging.config
import optparse
import os
import sys
import time
import traceback

import eventlet

# Install the _(...) function as a built-in so all other modules don't need to.
gettext.install('scalestack')

# Patch all the standard libs to support cooperative yielding through eventlet.
eventlet.monkey_patch()

__version__ = '0'
UNIQUE_ID_EXTRA = 0
DEFAULT_PATH = os.path.join(os.environ['HOME'], '.scalestack')
DEFAULT_LOGGING = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'}},
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'INFO'}},
    'root': {
        'handlers': ['console']}}
DEFAULT_THREAD_POOL_SIZE = 1000
DEFAULT_SERVICES = ['scalestack.http.Server']


class Core(object):
    '''Class to manage configuration, logging, and other shared resources.'''

    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        self.config_file = self.abspath('config')
        if os.path.exists(self.config_file):
            self.config = json.load(open(self.config_file, 'r'))
        else:
            self.config = {}
        self.services = {}
        self.force_log_level = None
        self.thread_pool = None

    def abspath(self, path):
        '''Make the given path absolute relative to the configure path.'''
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.path, path))

    def save_config(self):
        '''Save the current configuration to the file.'''
        json.dump(self.config, open(self.config_file, 'w'), indent=4)

    def config_get(self, name, default=None):
        '''Get a config value using dot notation.'''
        config = self.config
        for part in name.split('.'):
            part = '_%s' % part
            if part not in config:
                part = part[1:]
                if part not in config:
                    return default
            config = config[part]
        return config

    def config_set(self, name, value, local=False, overwrite=True):
        '''Set a config value using dot notation.'''
        config = self.config
        parts = name.split('.')
        last = parts.pop()
        if local and last[0] != '_':
            last = '_%s' % last
        for part in parts:
            part = '_%s' % part
            if part not in config:
                part = part[1:]
                if part not in config:
                    config[part] = {}
            config = config[part]
        if overwrite or last not in config:
            config[last] = value

    def get_service(self, service):
        '''Get a service, starting it first if needed.'''
        if service not in self.services:
            try:
                self.services[service] = import_class(service)(self)
            except Exception, exception:
                logging.getLogger().critical('Uncaught exception while '
                    'starting service %s: %s (%s)', service, exception,
                    ''.join(traceback.format_exc().split('\n')))
                raise SystemExit()
        return self.services[service]

    def run(self):
        '''Parse core config, load services, and start the main loop.'''
        self._setup_logging()
        thread_pool_size = self.config_get('thread_pool_size',
            DEFAULT_THREAD_POOL_SIZE)
        self.thread_pool = eventlet.GreenPool(size=thread_pool_size)
        logging.getLogger().info('Loading services')
        for service in self.config_get('services', DEFAULT_SERVICES):
            self.get_service(service)
        logging.getLogger().info('Starting event loop')
        try:
            self.thread_pool.waitall()
        except KeyboardInterrupt:
            pass
        except Exception, exception:
            logging.getLogger().critical('Uncaught exception in event loop: '
                '%s (%s)', exception,
                ''.join(traceback.format_exc().split('\n')))

    def _setup_logging(self):
        '''Set the forced logging level if it is set for all loggers.'''
        logging.config.dictConfig(self.config_get('logging', DEFAULT_LOGGING))
        if self.force_log_level is None:
            return
        logging.Logger.root.level = self.force_log_level
        for logger in logging.Logger.manager.loggerDict.itervalues():
            if not isinstance(logger, logging.Logger):
                continue
            logger.level = self.force_log_level
            for handler in logger.handlers:
                handler.level = self.force_log_level


class Common(object):
    '''Common base class for objects that use shared resources.'''

    def __init__(self, core):
        self.core = core
        logger_name = '%s.%s' % (self.__module__, self.__class__.__name__)
        self._log = logging.getLogger(logger_name)
        if self.core.force_log_level is not None:
            self._log.setLevel(self.core.force_log_level)


def import_class(module_name, class_name=None):
    '''Import a class given a full module.class name or seperate module and
    class names.'''
    if class_name is None:
        module_name, _separator, class_name = module_name.rpartition('.')
    try:
        __import__(module_name)
        return getattr(sys.modules[module_name], class_name)
    except (ImportError, ValueError, AttributeError), exception:
        raise ImportError(_('Class %s.%s cannot be imported (%s)') %
            (module_name, class_name, exception))


def unique_id():
    '''Make a fairly unique time-based 64bit integer (4k possible per
    microsecond).'''
    global UNIQUE_ID_EXTRA
    now = time.time()
    secs = int(now)
    micros = int((now - secs) * 1000000)
    unique = (secs << 32) + (micros << 12) + UNIQUE_ID_EXTRA
    UNIQUE_ID_EXTRA += 1
    if UNIQUE_ID_EXTRA >= 4096:
        UNIQUE_ID_EXTRA = 0
    return unique


def main():
    '''Setup a core object and start the core.'''
    parser = optparse.OptionParser(usage=_('Usage: scalestack [options]'))
    parser.add_option('-d', '--debug', action='store_true',
        help=_('Show debugging output'))
    parser.add_option('-p', '--path', default=DEFAULT_PATH,
        help=_('Location to keep all data files'))
    parser.add_option('-v', '--verbose', action='store_true',
        help=_('Show more verbose output'))
    (options, args) = parser.parse_args()
    core = Core(options.path)
    if options.debug:
        core.force_log_level = logging.DEBUG
    elif options.verbose:
        core.force_log_level = logging.INFO
    for arg in args:
        parts = arg.split('=', 1)
        if len(parts) == 1:
            parts.append('None')
        core.config_set(parts[0], parse_value(parts[1]))
    core.run()


def parse_value(value):  # pylint: disable=R0911,R0912
    '''Convert a string value to a native type.'''
    if value == '-':
        value = sys.stdin.read()
    if value == '':
        return value
    if value[0] == "'":
        return value.strip("'")
    if value[0] == '"':
        return value.strip('"')
    if value[0] == '[':
        value_list = value.strip('[] ')
        if value_list == '':
            return []
        return [parse_value(item) for item in value_list.split(',')]
    if value[0] == '{':
        result = {}
        for pair in value.strip('{} ').split(','):
            pair = pair.split('=')
            result[pair[0]] = parse_value(pair[1])
        return result
    if value.isdigit():
        return int(value)
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    if value.lower() == 'none':
        return None
    if value.startswith('eval:'):
        return eval(value[5:])
    if value.startswith('json:'):
        return json.loads(value[5:])
    return value


if __name__ == '__main__':
    main()
