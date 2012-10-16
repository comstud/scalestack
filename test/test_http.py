'''Unittests for HTTP service.'''

import unittest

import test


class TestHTTP(unittest.TestCase):
    '''Test case for HTTP service.'''

    def test_basic(self):
        response = test.request('GET', '/')
        self.assertEquals(404, response.status)
        self.assertEquals('404 Not Found', response.read())
