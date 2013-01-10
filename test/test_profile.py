'''Unittests for profile service.'''

import unittest

import test


class TestProfile(unittest.TestCase):
    '''Test case for profile service.'''

    def test_basic(self):
        response = test.request('GET', '/profile')
        self.assertEquals(200, response.status)
