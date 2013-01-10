'''Unittests for file service.'''

import os
import unittest

import test


class TestFile(unittest.TestCase):
    '''Test case for file service.'''

    def test_basic(self):
        response = test.request('GET', '/UNLICENSE')
        self.assertEquals(200, response.status)
        self.assertEquals(os.stat('UNLICENSE').st_size, len(response.read()))
