#!/usr/bin/env python3
import unittest

class TestSanity(unittest.TestCase):
    def setUp(self):
        self.right_answer = 4

    def test_sanity(self):
        self.assertEqual(2 + 2, self.right_answer)

if __name__ == '__main__':
    unittest.main()
