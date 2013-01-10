'''File service for the HTTP service.'''

import os

import scalestack.http

CONFIG_OPTIONS = {
    'map': scalestack.Option([],
        _('List of objects where each object is mapping with host, path, and '
        'file_path settings.')),
    'read_size': scalestack.Option(65536,
        _('Size to read files with while streaming.'))}


class Service(scalestack.Common):
    '''File service.'''

    def __init__(self, core):
        super(Service, self).__init__(core)
        http = self.core.get_service('scalestack.http')
        for entry in self._get_config('map'):
            path = entry.get('path', '/')
            extra_env = {
                'scalestack.file.path': path,
                'scalestack.file.file_path': entry.get('file_path', '/www')}
            handler = scalestack.http.Handler(entry.get('host', None), path,
                Request, extra_env)
            http.add_handler(handler)


class Request(scalestack.http.Request):
    '''Request handler for file service.'''

    def run(self):
        '''Run the request.'''
        path = self._env.get('PATH_INFO')
        if path is None or path.find('/.') != -1:
            raise scalestack.http.NotFound()
        prefix = self._env.get('scalestack.file.path')
        path = path[len(prefix):].lstrip('/')
        file_path = self._env.get('scalestack.file.file_path')
        file_path = os.path.join(file_path, path)
        if not os.path.isfile(file_path):
            raise scalestack.http.NotFound()
        file_stream = open(file_path)
        read_size = self._get_config('read_size')
        return self._ok(iter(lambda: file_stream.read(read_size), ''))
