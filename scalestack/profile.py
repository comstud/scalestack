'''Profile service.'''

import math
import sys
import time

import scalestack.http

CONFIG_OPTIONS = {
    'http_host': scalestack.Option(None, _('Host for profile page.')),
    'http_path': scalestack.Option('/profile', _('Path for profile page.')),
    'recent_size': scalestack.Option(100,
        _('Number of recent profile entries to keep'))}


class Service(scalestack.Common):
    '''Profile service.'''

    def __init__(self, core):
        super(Service, self).__init__(core)
        self.recent = []
        http = self.core.get_service('scalestack.http')
        handler = scalestack.http.Handler(self._get_config('http_host'),
            self._get_config('http_path'), Request)
        http.add_handler(handler)


class Request(scalestack.http.Request):
    '''Request handler for profile service.'''

    def run(self):
        '''Run the request.'''
        self._headers.append(('Content-Type', 'text/plain'))
        return self._ok(self._recent())

    def _recent(self):
        '''Print all recent profile entries.'''
        for profile in reversed(self._get_service().recent):
            yield '%s\n' % profile


class Profile(scalestack.Common):
    '''Class used to profile different metrics.'''

    def __init__(self, core, prefix='profile', last_cpu=None, last_time=None):
        super(Profile, self).__init__(core)
        self._prefix = prefix
        self._last_cpu = last_cpu or time.clock()
        self._last_time = last_time or time.time()
        self.marks = {}
        recent = self._get_service().recent
        recent.append(self)
        while len(recent) > self._get_config('recent_size'):
            recent.pop(0)

    def mark(self, name, value):
        '''Mark an arbitrary value.'''
        if name not in self.marks:
            self.marks[name] = 0.0
        self.marks[name] += value

    def mark_cpu(self, name, value=None):
        '''Mark the CPU time since the last call for the given name.'''
        if value is None:
            now = time.clock()
            value = now - self._last_cpu
            self._last_cpu = now
        self.mark('%s:cpu' % name, value)

    def mark_time(self, name, value=None):
        '''Mark the time since the last call for the given name.'''
        if value is None:
            now = time.time()
            value = now - self._last_time
            self._last_time = now
        self.mark('%s:time' % name, value)

    def mark_all(self, name):
        '''Mark all metrics with default values.'''
        self.mark_cpu(name)
        self.mark_time(name)

    def __repr__(self):
        times = ' '.join(['%s=%.3f' % (name, value)
            for name, value in self.marks.iteritems()])
        return '%s %s' % (self._prefix, times)


def report(log):
    '''Print a report of multiple timer outputs.'''
    data = report_data(log)
    print '    Count       Avg       Min       Max    StdDev     Total'
    for name in sorted(data.keys()):
        formatted = dict(name=name)
        for key, value in data[name].iteritems():
            if isinstance(value, list):
                continue
            if value > 100 or value == int(value):
                formatted[key] = '%d' % value
            else:
                formatted[key] = '%.3f' % value
        print '%(count)9s %(average)9s %(min)9s %(max)9s %(stddev)9s ' \
            '%(total)9s  %(name)s' % formatted


def report_data(log):
    '''Collect and summarize the report data.'''
    data = {}
    while True:
        line = log.readline()
        if not line:
            break
        for part in line.split(' '):
            part = part.split('=')
            if part[0] == '' or len(part) != 2:
                continue
            name = part[0]
            try:
                value = float(part[1])
            except ValueError:
                continue
            if name not in data:
                data[name] = dict(count=1, values=[value], total=value,
                    min=value, max=value)
            else:
                data[name]['count'] += 1
                data[name]['values'].append(value)
                data[name]['total'] += value
                if value < data[name]['min']:
                    data[name]['min'] = value
                if value > data[name]['max']:
                    data[name]['max'] = value
    for name, name_data in data.iteritems():
        variance = 0
        average = data[name]['total'] / data[name]['count']
        for value in name_data['values']:
            variance += math.pow(value - average, 2)
        data[name]['average'] = average
        data[name]['variance'] = variance
        data[name]['stddev'] = math.sqrt(variance / data[name]['count'])
    return data


def main():
    '''Print report for data from logs or stdin.'''
    if len(sys.argv) == 1:
        report(sys.stdin)
    else:
        for log in sys.argv:
            report(open(log))


if __name__ == '__main__':
    main()
