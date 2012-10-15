'''Unittests for HTTP server and request processing.'''

import unittest

import test


class TestHTTP(unittest.TestCase):
    '''Test case for HTTP server.'''

    def test_basic(self):
        response = test.request('GET', '/')
        self.assertEquals(200, response.status)
        self.assertEquals('test', response.read())
