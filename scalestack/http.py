'''HTTP service based on eventlet.wsgi.'''

import Cookie
import socket
import traceback

import eventlet.wsgi

import scalestack

CONFIG_OPTIONS = {
    'host': scalestack.Option(str, '', _('Host to bind to.')),
    'port': scalestack.Option(int, 80, _('Port to bind to.')),
    'backlog': scalestack.Option(int, 64,
        _('Number of connections to keep in baclog for listening socket.')),
    'request_log_format': scalestack.Option(str,
        '%(client_ip)s "%(request_line)s" %(status_code)s %(body_length)s '
        '%(wall_seconds).3f',
        _('Request log format, for details see the log_format option at: '
        'http://eventlet.net/doc/modules/wsgi.html')),
    'server_name': scalestack.Option(str, 'ScaleStack',
        _('Name to use in Server response header.'))}


class Service(scalestack.Common):
    '''HTTP service class.'''

    def __init__(self, core):
        super(Service, self).__init__(core)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._get_config('host'), self._get_config('port')))
        server.listen(self._get_config('backlog'))
        self._log.info(_('Listening on %s'), server.getsockname())

        log = EventletWSGILog(self._log)

        def log_message(self, message, *args):
            '''Hack to capture log lines that eventlet doesn't wrap.'''
            log.write('%s %s\n' % (self.client_address[0], message % args))

        eventlet.wsgi.HttpProtocol.log_message = log_message
        self.core.thread_pool.spawn_n(eventlet.wsgi.server, server, self,
            log=log, log_format=self._get_config('request_log_format'),
            custom_pool=self.core.thread_pool)

    def __call__(self, env, start):
        '''Entry point for all requests. Wrap all exceptions with an internal
        server error.'''
        try:
            return Request(env, start, self.core).run()
        except StatusCode, exception:
            found = False
            for header in exception.headers:
                if header[0] == 'Server':
                    found = True
                    break
            if not found:
                exception.headers.insert(0,
                    ('Server', self._get_config('server_name')))
            start(exception.status, exception.headers)
            self._log.warning(_('Status code: %s'), exception)
            return exception.body
        except Exception, exception:
            self._log.error('Uncaught exception in request: %s (%s)',
                exception, ''.join(traceback.format_exc().split('\n')))
            start(_('500 Internal Server Error'),
                [('Server', self._get_config('server_name'))])
            return ''


class EventletWSGILog(object):
    '''Class for eventlet.wsgi.server to forward logging messages.'''

    def __init__(self, log):
        self._log = log

    def write(self, message):
        '''Write WSGI log message to main log.'''
        self._log.info(message.rstrip())


class Request(scalestack.Common):
    '''Request class used by the WSGI server.'''

    def __init__(self, env, start, core):
        super(Request, self).__init__(core)
        self._env = env
        self._start = start
        self._method = env['REQUEST_METHOD'].upper()
        self._parameters = None
        self._cookies = None
        self._body = None
        self._headers = [('Server', self._get_config('server_name'))]

    def run(self):
        '''Run the request.'''
        return self._ok('test')

    def _read_body(self):
        '''Read the request body.'''
        if self._body is not None:
            return
        try:
            self._body = self._env['wsgi.input'].read()
        except Exception, exception:
            self._log.error(_('Error reading request body: %s'), exception)
            raise BadRequest(_('Error reading request body'))

    def _parse_parameters(self):
        '''Parse the URL parameter list into a dictionary.'''
        if self._parameters is not None:
            return
        self._parameters = {}
        parameters = self._env.get('QUERY_STRING')
        if parameters is None:
            return
        for parameter in parameters.split('&'):
            parameter = parameter.split('=', 1)
            key = parameter[0].strip()
            if len(parameter) == 1:
                self._parameters[key] = None
            else:
                self._parameters[key] = parameter[1].strip()

    def _parse_cookies(self):
        '''Parse the cookie header into a dictionary.'''
        if self._cookies is not None:
            return
        self._cookies = {}
        cookies = self._env.get('HTTP_COOKIE')
        if cookies is None:
            return
        for cookie in cookies.split(';'):
            cookie = cookie.split('=', 1)
            key = cookie[0].strip()
            if len(cookie) == 1:
                self._cookies[key] = None
            else:
                self._cookies[key] = cookie[1].strip(' \t"')

    def _set_cookie(self, name, value, expires=None, path=None, domain=None):
        '''Set a cookie in the response headers.'''
        cookie = Cookie.SimpleCookie()
        cookie[name] = value
        if expires is not None:
            cookie[name]['expires'] = expires
        if path is not None:
            cookie[name]['path'] = path
        if domain is not None:
            cookie[name]['domain'] = path
        self._headers.append(('Set-Cookie', cookie[name].OutputString()))

    def _respond(self, status, body=None):
        '''Start response with the given status.'''
        self._start(status, self._headers)
        return body or ''

    def _ok(self, body=None):
        '''Start a 200 response.'''
        return self._respond(_('200 Ok'), body)

    def _created(self, body=None):
        '''Start a 201 response.'''
        return self._respond(_('201 Created'), body)

    def _no_content(self, body=None):
        '''Start a 204 response.'''
        return self._respond(_('204 No Content'), body)


class StatusCode(Exception):
    '''Base exception for HTTP response status codes.'''

    status = '000 Undefined'

    def __init__(self, body=None, headers=None):
        self.headers = headers or []
        self.body = body or ''
        super(StatusCode, self).__init__(_('status=%s headers=%s body=%s') %
            (self.status, headers, body))


class BadRequest(StatusCode):
    '''Exception for a 400 response.'''

    status = _('400 Bad Request')


class Unauthorized(StatusCode):
    '''Exception for a 401 response.'''

    status = _('401 Unauthorized')


class Forbidden(StatusCode):
    '''Exception for a 403 response.'''

    status = _('403 Forbidden')


class NotFound(StatusCode):
    '''Exception for a 404 response.'''

    status = _('404 Not Found')


class MethodNotAllowed(StatusCode):
    '''Exception for a 405 response.'''

    status = _('405 Method Not Allowed')
