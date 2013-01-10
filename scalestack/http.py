'''HTTP service based on gevent.pywsgi.'''

import Cookie
import traceback

import gevent.pywsgi

import scalestack

CONFIG_OPTIONS = {
    'host': scalestack.Option('', _('Host to bind to.')),
    'port': scalestack.Option(80, _('Port to bind to.')),
    'backlog': scalestack.Option(64,
        _('Number of connections to keep in baclog for listening socket.')),
    'server_name': scalestack.Option('ScaleStack/%s' % scalestack.__version__,
        _('Name to use in Server response header.'))}


class WSGIHandler(gevent.pywsgi.WSGIHandler):
    '''Wrapper to do custom logging.'''

    def log_request(self):
        '''Log a request.'''
        log = self.server.log['access']
        log.info(self.format_request())

    def log_error(self, msg, *args):
        '''Log an error.'''
        log = self.server.log['error']
        log.warning(msg, *args)


class Handler(object):
    '''Options and request class for handlers.'''

    def __init__(self, host, path, request_class, *args, **kwargs):
        if path[0] != '/':
            path = '/%s' % path
        self.host = host
        self.path = path
        self.request_class = request_class
        self.args = args
        self.kwargs = kwargs


class Service(scalestack.Common):
    '''HTTP service class.'''

    def __init__(self, core):
        super(Service, self).__init__(core)
        self._handlers = []
        log = {
            'access': self.core.get_logger('scalestack.http.access'),
            'error': self._log}
        self._server = gevent.pywsgi.WSGIServer(
            (self._get_config('host'), self._get_config('port')), self,
            backlog=self._get_config('backlog'), log=log,
            handler_class=WSGIHandler)
        self._server.set_environ(
            {'SERVER_SOFTWARE': self._get_config('server_name')})
        self._server.start()
        self._log.info(_('Listening on %s:%d'), self._server.server_host,
            self._server.server_port)

    def add_handler(self, handler):
        '''Add a handler to the service, making sure it doesn't exist.'''
        if self.match_handler(handler.host, handler.path, True) is not None:
            raise HandlerAlreadyExists('%s %s' % handler.host, handler.path)
        self._handlers.append(handler)
        self._log.info(_('Added handler: %s %s'), handler.host, handler.path)

    def match_handler(self, host, path, exact=False):
        '''Find the best match for a given host and path.'''
        match = None
        for handler in self._handlers:
            if host != handler.host and (exact or handler.host is not None):
                continue
            if exact:
                if path == handler.path:
                    return handler
                continue
            if match is not None and len(match.path) > len(handler.path):
                continue
            if path.startswith(handler.path):
                match = handler
        return match

    def __call__(self, env, start):
        '''Entry point for all requests. Wrap all exceptions with an internal
        server error.'''
        host = env.get('HTTP_HOST', None)
        if host is not None:
            host = host.rsplit(':', 1)[0]
        path = env.get('PATH_INFO', '/')
        handler = self.match_handler(host, path)
        try:
            if handler is None:
                self._log.info(_('No handler found for %s %s'), host, path)
                raise NotFound()
            request = handler.request_class(env, start, self.core,
                *handler.args, **handler.kwargs)
            return request.run()
        except StatusCode, exception:
            if not header_exists('Server', exception.headers):
                exception.headers.insert(0, ('Server', env['SERVER_SOFTWARE']))
            start(exception.status, exception.headers)
            self._log.warning(_('Status code: %s'), exception)
            return exception.body
        except Exception, exception:
            self._log.error(_('Uncaught exception in request: %s (%s)'),
                exception, ''.join(traceback.format_exc().split('\n')))
            start(_('500 Internal Server Error'),
                [('Server', env['SERVER_SOFTWARE'])])
            return ''


class Request(scalestack.Common):
    '''Request class used by the WSGI server.'''

    def __init__(self, env, start, core, extra_env=None):
        super(Request, self).__init__(core)
        self._env = env
        if extra_env is not None:
            self._env.update(extra_env)
        self._start = start
        self._method = env['REQUEST_METHOD'].upper()
        self._parameters = None
        self._cookies = None
        self._body = None
        self._headers = [('Server', self._env['SERVER_SOFTWARE'])]

    def run(self):
        '''Run the request.'''
        raise NotImplementedError()  # pragma: no cover

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
        self._log.debug(_('Request details: status=%s headers=%s'), status,
            self._headers)
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
        self.body = body or self.status
        if body is None and not header_exists('Content-Type', self.headers):
            self.headers.append(('Content-Type', 'text/plain'))
        super(StatusCode, self).__init__(_('status=%s headers=%s') %
            (self.status, headers))


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


class HandlerAlreadyExists(Exception):
    '''Exception raised when a handler already exists.'''

    pass


def header_exists(name, headers):
    '''Check to see if a header exists in a list of headers.'''
    for header in headers:
        if header[0] == name:
            return True
    return False
