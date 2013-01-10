'''Core services and base classes for the scalestack package. Also handle
option parsing and starting the core when run from the command line.'''

# Patch all the standard libs to support cooperative yielding through gevent.
import gevent.monkey
gevent.monkey.patch_all()

import gettext
import json
import logging.config
import optparse
import os
import sys
import time
import traceback

# Install the _(...) function as a built-in so all other modules don't need to.
gettext.install('scalestack')

__version__ = '0'


class Option(object):
    '''Details for config options.'''

    def __init__(self, default, description):
        self.default = default
        self.description = description


class Common(object):
    '''Common base class for objects that use shared resources.'''

    def __init__(self, core):
        self.core = core
        self._log = self.core.get_logger(self.__module__)
        self._log.debug(_('%s instance created'), self.__class__.__name__)

    def _get_config(self, option):
        '''Get config options for this module.'''
        return self.core.get_config(self.__module__, option)

    def _get_service(self):
        '''Get service for this module.'''
        return self.core.get_service(self.__module__)


DEFAULT_CONFIG_FILE = os.path.join(os.environ['HOME'], '.scalestack')
DEFAULT_CONFIG = {'scalestack.http': {}}
CONFIG_OPTIONS = {
    'logging': Option({
        'version': 1,
        'formatters': {
            'default': {
                'format': '%(asctime)s %(levelname)s %(process)d %(name)s '
                    '%(message)s'}},
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
                'level': 'INFO'}},
        'root': {
            'handlers': ['console']}},
        _('Logging schema to use, for details see: '
        'http://docs.python.org/library/logging.config.html')),
    'processes': Option(1,
        _('Number of processes to run as one services are started.'))}


class Core(object):
    '''Class to manage configuration, logging, services, and the event loop.'''

    def __init__(self, config_file=None):
        self.config_file = config_file or DEFAULT_CONFIG_FILE
        self.config = {'scalestack': {}}
        self.services = {'scalestack': self}
        self.force_log_level = None
        self.running = False
        self._log = None
        if os.path.isfile(self.config_file):
            self.config.update(json.load(open(self.config_file, 'r')))
        else:
            self.config.update(DEFAULT_CONFIG)
        for service in self.config:
            for option in self.config[service]:
                self.verify_config(service, option)

    def save_config(self):
        '''Save the current configuration to the file.'''
        json.dump(self.config, open(self.config_file, 'w'), indent=4)
        if self.running:
            self._log.info(_('Saved config to file: %s'), self.config_file)

    def get_config(self, service, option):
        '''Get a config value if set or the default.'''
        self.verify_config(service, option)
        if service in self.config:
            if option in self.config[service]:
                return self.config[service][option]
        return sys.modules[service].CONFIG_OPTIONS[option].default

    def _get_config(self, option):
        '''Get config options for the core service.'''
        return self.get_config('scalestack', option)

    def set_config(self, service, option, value, overwrite=True):
        '''Set a config value.'''
        self.verify_config(service, option)
        if overwrite or option not in self.config:
            self.config[service][option] = value
            if self.running:
                self._log.debug(_('Set config option: %s.%s=%s'), service,
                    option, value)

    def verify_config(self, service, option):
        '''Ensure the given service option is valid.'''
        self.load_service(service)
        if option not in sys.modules[service].CONFIG_OPTIONS:
            raise InvalidConfigOption('%s.%s' % (service, option))

    def get_logger(self, name):
        '''Get a logger.'''
        logger = logging.getLogger(name)
        if self.force_log_level is not None:
            logger.setLevel(self.force_log_level)
        return logger

    def load_service(self, service):
        '''Load a service.'''
        if service in self.services:
            return
        try:
            __import__(service)
            self.services[service] = getattr(sys.modules[service], 'Service')
            if service not in self.config:
                self.config[service] = {}
        except (ImportError, ValueError, AttributeError), exception:
            raise ImportError(_('Cannot import %s.Service (%s)') %
                (service, exception))
        if self.running:
            self.start_service(service)

    def start_service(self, service):
        '''Start a service, loading it first if needed.'''
        self.load_service(service)
        if service != 'scalestack' and \
            not hasattr(self.services[service], 'core'):
            self.services[service] = self.services[service](self)
            self._log.info(_('Started service: %s'), service)

    def get_service(self, service):
        '''Get a service, loading it first if needed.'''
        if not self.running:
            return None
        self.start_service(service)
        return self.services[service]

    def run(self):
        '''Start logging, load services, and start the event loop.'''
        self._setup_logging()
        self._log.info(_('Starting services'))
        self.running = True
        for service in self.config:
            self.start_service(service)
        self._log.info(_('Starting event loop'))
        self._setup_processes()
        try:
            while True:
                time.sleep(60)
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

    def _setup_processes(self):
        '''Start extra processes if needed.'''
        for _process in xrange(1, self._get_config('processes')):
            if os.fork() == 0:
                return
            self._log.info(_('Processes started with PID %d'), os.getpid())


class ServiceNotLoaded(Exception):
    '''Exception raised when a service was requested but was not loaded.'''

    pass


class InvalidConfigOption(Exception):
    '''Exception raised when a configuration option is not valid.'''

    pass


HELP_TEXT = _('''
Service configuration may be given by using the syntax:

    <service>.<option>=<value>

For example, to use a different port for the scalestack.http service, give the
following argument:

    scalestack.http.port=8080

Available options:
''')


def main():
    '''Setup a core object and start the core.'''
    parser = optparse.OptionParser(usage=_('Usage: scalestack [options]'),
        add_help_option=False)
    parser.add_option('-c', '--config', default=DEFAULT_CONFIG_FILE,
        help=_('Config file to use'))
    parser.add_option('-d', '--debug', action='store_true',
        help=_('Show debugging output'))
    parser.add_option('-h', '--help', action='store_true',
        help=_('Show this help message and exit'))
    parser.add_option('-v', '--verbose', action='store_true',
        help=_('Show more verbose output'))
    parser.add_option('-V', '--version', action='store_true',
        help=_('Print version and exit'))
    (options, args) = parser.parse_args()
    if options.version:
        print __version__
        return
    core = Core(options.config)
    if options.debug:
        core.force_log_level = logging.DEBUG
    elif options.verbose:
        core.force_log_level = logging.INFO
    for arg in args:
        parts = arg.split('=', 1)
        if len(parts) == 1:
            # If no value is given, just load the service.
            core.load_service(parts[0])
        else:
            (service, option) = parts[0].rsplit('.', 1)
            core.set_config(service, option, parse_value(parts[1]))
    if options.help:
        parser.print_help()
        print HELP_TEXT
        for service in sorted(core.services):
            for option_name in sorted(sys.modules[service].CONFIG_OPTIONS):
                option = sys.modules[service].CONFIG_OPTIONS[option_name]
                print _('%s.%s - %s (default=%s)') % (service, option_name,
                    option.description, json.dumps(option.default, indent=4))
        return
    try:
        core.run()
    except Exception, exception:  # pylint: disable=W0703
        error = _('Uncaught exception in core: %s (%s)') % \
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
    if value.isdigit():
        return int(value)
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    if value.lower() == 'none':
        return None
    if value[0] == '[' or value[0] == '{':
        return json.loads(value)
    if value.startswith('json:'):
        return json.loads(value[5:])
    return value


if __name__ == '__main__':
    main()
