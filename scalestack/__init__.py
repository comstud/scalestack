'''Core services for the scalestack package. Also handle option parsing
and starting the core when run from the command line.'''

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


class Option(object):
    '''Details for config options.'''

    def __init__(self, value_type, default_value, help_text):
        self.value_type = value_type
        self.default_value = default_value
        self.help_text = help_text


class Common(object):
    '''Common base class for objects that use shared resources.'''

    def __init__(self, core):
        self.core = core
        self._log = logging.getLogger(self.__module__)
        if self.core.force_log_level is not None:
            self._log.setLevel(self.core.force_log_level)

    def _get_config(self, option):
        '''Get config options for this module.'''
        return self.core.get_config(self.__module__, option)


CONFIG_OPTIONS = {
    'logging': Option(dict, {
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
            'handlers': ['console']}},
        'Logging schema to use, for details see: '
        'http://docs.python.org/library/logging.config.html'),
    'thread_pool_size': Option(int, 1000,
        'Number of threads to use for the thread pool.')}
DEFAULT_PATH = os.path.join(os.environ['HOME'], '.scalestack')
DEFAULT_CONFIG = {'scalestack.http': {}}


class Core(object):
    '''Class to manage configuration, logging, services, and the event loop.'''

    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        self.config_file = self.abspath('config')
        if os.path.exists(self.config_file):
            self.config = json.load(open(self.config_file, 'r'))
        else:
            self.config = DEFAULT_CONFIG
        self.services = {'scalestack': self}
        self.thread_pool = eventlet.GreenPool()
        self.force_log_level = None
        self.running = False
        self._log = None

    def abspath(self, path):
        '''Make the given path absolute relative to the configure path.'''
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.path, path))

    def save_config(self):
        '''Save the current configuration to the file.'''
        json.dump(self.config, open(self.config_file, 'w'), indent=4)
        self._log.info(_('Saved config to file: %s'), self.config_file)

    def get_config(self, service, option):
        '''Get a config value if set or the default.'''
        self.verify_config(service, option)
        if service in self.config:
            local_option = '_%s' % option
            if local_option in self.config[service]:
                return self.config[service][local_option]
            if option in self.config[service]:
                return self.config[service][option]
        return sys.modules[service].CONFIG_OPTIONS[option].default_value

    def _get_config(self, option):
        '''Get config options for the core service.'''
        return self.get_config('scalestack', option)

    def set_config(self, service, option, value, overwrite=True):
        '''Set a config value.'''
        self.verify_config(service, option)
        if service not in self.config:
            self.config[service] = {}
        if overwrite or option not in self.config:
            self.config[service][option] = value
            if self.running:
                self._log.info(_('Set config option: %s.%s=%s'), service,
                    option, value)

    def verify_config(self, service, option):
        '''Ensure the given service option is valid.'''
        self.load_service(service)
        if option not in sys.modules[service].CONFIG_OPTIONS:
            raise InvalidConfigOption('%s.%s' % (service, option))

    def load_service(self, service):
        '''Load a service.'''
        if service in self.services:
            return
        try:
            __import__(service)
            self.services[service] = getattr(sys.modules[service], 'Service')
        except (ImportError, ValueError, AttributeError), exception:
            raise ImportError(_('Cannot be imported %s.Service (%s)') %
                (service, exception))
        if self.running:
            self.start_service(service)

    def start_service(self, service):
        '''Start a service, loading it first if needed.'''
        if service not in self.services:
            self.load_service(service)
        if service != 'scalestack':
            self.services[service] = self.services[service](self)
            self._log.info(_('Started service: %s'), service)

    def get_service(self, service):
        '''Get a service, loading it first if needed.'''
        if service not in self.services:
            self.load_service(service)
        return self.services[service]

    def run(self):
        '''Start logging, load services, and start the event loop.'''
        self._setup_logging()
        self.thread_pool.resize(self._get_config('thread_pool_size'))
        self._log.info(_('Starting services'))
        self.running = True
        for service in self.config:
            self.start_service(service)
        self._log.info(_('Starting event loop'))
        try:
            self.thread_pool.waitall()
        except KeyboardInterrupt:
            pass

    def _setup_logging(self):
        '''Set the forced logging level if it is set for all loggers.'''
        logging.config.dictConfig(self._get_config('logging'))
        self._log = logging.getLogger('scalestack')
        if self.force_log_level is None:
            return
        logging.Logger.root.level = self.force_log_level
        for logger in logging.Logger.manager.loggerDict.itervalues():
            if not isinstance(logger, logging.Logger):
                continue
            logger.setLevel(self.force_log_level)
            for handler in logger.handlers:
                handler.setLevel(self.force_log_level)


class ServiceNotLoaded(Exception):
    '''Exception raised when a service was requested but was not loaded.'''

    pass


class InvalidConfigOption(Exception):
    '''Exception raised when a configuration option is not valid.'''

    pass


UNIQUE_ID_EXTRA = 0


def get_unique_id():
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


def parse_unique_id(unique_id):
    '''Parse a unique ID into it's parts.'''
    return (unique_id >> 32, (unique_id >> 12) & 1048575, unique_id & 4095)


HELP_TEXT = _('''
Service configuration may be given by using the syntax:

    <service>.<option>=<value>

For example, to use a different port for the scalestack.http service, give the
following argument:

    scalestack.http.port=8080

Configuration given is stored in the main config hash, so it will be included
if the configuration is saved to a file. Local only options (those not
propagated via remote interfaces) may be given by using a '_' prefix on the
option name. For example:

    scalestack.http._port=8080

Available options:
''')


def main():
    '''Setup a core object and start the core.'''
    parser = optparse.OptionParser(usage=_('Usage: scalestack [options]'),
        add_help_option=False)
    parser.add_option('-d', '--debug', action='store_true',
        help=_('Show debugging output'))
    parser.add_option('-h', '--help', action='store_true',
        help='Show this help message and exit')
    parser.add_option('-p', '--path', default=DEFAULT_PATH,
        help=_('Location to keep all data files'))
    parser.add_option('-v', '--verbose', action='store_true',
        help=_('Show more verbose output'))
    parser.add_option('-V', '--version', action='store_true',
        help=_('Print version and exit'))
    (options, args) = parser.parse_args()
    if options.version:
        print __version__
        return
    core = Core(options.path)
    if options.debug:
        core.force_log_level = logging.DEBUG
    elif options.verbose:
        core.force_log_level = logging.INFO
    for arg in args:
        parts = arg.split('=', 1)
        if len(parts) == 1:
            parts.append('{}')
        (service, option) = parts[0].rsplit('.', 1)
        core.set_config(service, option, parse_value(parts[1]))
    if options.help:
        parser.print_help()
        print HELP_TEXT
        for service in sorted(core.services):
            for option_name in sorted(sys.modules[service].CONFIG_OPTIONS):
                option = sys.modules[service].CONFIG_OPTIONS[option_name]
                print _('%s.%s=%s\n\n    %s\n    (default=%s)\n') % (service,
                    option_name, str(option.value_type)[7:-2],
                    option.help_text, option.default_value)
        return
    try:
        print core.config
        core.run()
    except Exception, exception:  # pylint: disable=W0703
        error = _('Uncaught exception in event loop: %s (%s)') % \
            (exception, ''.join(traceback.format_exc().split('\n')))
        logging.getLogger().critical(error)
        sys.stderr.write('\n%s\n' % error)


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
    if value.startswith('json:'):
        return json.loads(value[5:])
    return value


if __name__ == '__main__':
    main()
