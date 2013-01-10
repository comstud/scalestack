'''File service.'''

import os

import scalestack.http
import scalestack.profile

CONFIG_OPTIONS = {
    'map': scalestack.Option([],
        _('List of objects where each object is mapping with host, path, and '
        'file_path settings.')),
    'mime_types': scalestack.Option('/etc/mime.types', _('Mime types file')),
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

        self.mime_types = {}
        mime_types = self._get_config('mime_types')
        if not os.path.isfile(mime_types):
            return
        mime_types = open(mime_types)
        while True:
            parts = mime_types.readline()
            if parts == '':
                break
            parts = parts.split()
            for extension in parts[1:]:
                self.mime_types[extension] = parts[0]


class Request(scalestack.http.Request):
    '''Request handler for file service.'''

    def run(self):
        '''Run the request.'''
        profile = scalestack.profile.Profile(self.core, 'file_request')
        path = self._env.get('PATH_INFO')
        if path is None or path.find('/.') != -1:
            raise scalestack.http.NotFound()
        prefix = self._env.get('scalestack.file.path')
        path = path[len(prefix):].lstrip('/')
        file_path = self._env.get('scalestack.file.file_path')
        file_path = os.path.join(file_path, path)
        profile.mark_all('parse')

        if not os.path.isfile(file_path):
            raise scalestack.http.NotFound()

        extension = file_path.rsplit('.', 1)[0]
        mime_types = self._get_service().mime_types
        if extension in mime_types:
            self._headers.append(('Content-Type', mime_types[extension]))
        stream = open(file_path)
        profile.mark_time('open')
        return self._ok(self._stream(stream, self._get_config('read_size'),
            profile))
