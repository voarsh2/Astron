#!/usr/bin/env python3
import unittest
from common.unittests import ConfigTest
from common.dcfile import *

class TestConfigStateServer(ConfigTest):
    def test_stateserver_good(self):
        config = """\
            messagedirector:
                bind: 127.0.0.1:57123
            general:
                dc_files:
                    - %r
            roles:
                - type: stateserver
                  control: 100100
            """ % test_dc
        self.assertEqual(self.checkConfig(config), 'Valid')

    def test_ss_invalid_attr(self):
        config = """\
            messagedirector:
                bind: 127.0.0.1:57123

            roles:
                - type: stateserver
                  queque: "pu-pu"
            """
        self.assertEqual(self.checkConfig(config), 'Invalid')

    def test_ss_invalid_control(self):
        config = """\
            messagedirector:
                bind: 127.0.0.1:57123

            roles:
                - type: stateserver
                  control: 0
            """
        self.assertEqual(self.checkConfig(config), 'Invalid')

    def test_ss_reserved_control(self):
        config = """\
            messagedirector:
                bind: 127.0.0.1:57123

            roles:
                - type: stateserver
                  control: 100
            """
        self.assertEqual(self.checkConfig(config), 'Invalid')

if __name__ == '__main__':
    unittest.main()
