#!/usr/bin/env python3
import unittest, socket, os, json, tempfile
from common.astron import *
from common.dcfile import *

LOG_WAIT_TIMEOUT = 5.0
NETWORK_ADDR = ('127.0.0.1', 19090)
MD_ADDR = ('127.0.0.1',  57123)

CONFIG = """\
messagedirector:
    bind: 127.0.0.1:57123

general:
    eventlogger: 127.0.0.1:19090

roles:
    - type: eventlogger
      bind: 127.0.0.1:19090
      output: %s
"""

STANDARD_EVENT = b'\x82\xa3bar\xa3baz\xa4type\xa3foo' # MessagePack formatted event
NONSTANDARD_MSGPACK = b'{'

@unittest.skipIf('MANUAL_LAUNCH_CONFIG' in os.environ,
                 'EventLogger tests require captured test daemon output')
class TestEventLogger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logHandle, cls.log_file = tempfile.mkstemp(prefix = 'astron-', suffix = '.log')
        os.close(logHandle)
        cls.addClassCleanup(os.remove, cls.log_file)

        cls.daemon = Daemon(CONFIG % cls.log_file)
        cls.addClassCleanup(cls.daemon.stop)
        cls.daemon.start()

        cls.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cls.addClassCleanup(cls.socket.close)

        md_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        md_socket.connect(MD_ADDR)
        cls.mdsocket = MDConnection(md_socket)
        cls.addClassCleanup(cls.mdsocket.close)
        cls.waitForLogLines(1) # Wait for the EventLogger's startup event.

    @classmethod
    def numLinesLog(cls):
        with open(cls.log_file, "r") as log:
            return len(log.read().splitlines())

    @classmethod
    def waitForLogLines(cls, count):
        # EventLogger emits this test signal after flushing its output file. Waiting
        # on Astron's captured output avoids polling the file or sleeping.
        cls.daemon.wait_for_output_count(
            'ASTRON_TEST_EVENTLOGGER_ENTRY_WRITTEN', count, timeout=LOG_WAIT_TIMEOUT
        )

    def test_writesToLog(self):
        numLines1 = self.numLinesLog()

        self.socket.sendto(STANDARD_EVENT, NETWORK_ADDR)
        self.waitForLogLines(numLines1 + 1)

        self.assertEqual(self.numLinesLog(), numLines1 + 1) # exactly one line is added

    def test_ignoresNonJSON(self):
        numLines1 = self.numLinesLog()

        self.socket.sendto(NONSTANDARD_MSGPACK, NETWORK_ADDR)
        # The valid datagram sent from the same UDP socket is a processing
        # canary; once it is logged, the preceding invalid datagram was handled.
        self.socket.sendto(STANDARD_EVENT, NETWORK_ADDR)
        self.waitForLogLines(numLines1 + 1)

        self.assertEqual(self.numLinesLog(), numLines1 + 1) # only the canary was logged

    def test_ignoresNonMsgpack(self):
        numLines1 = self.numLinesLog()

        self.socket.sendto(b"123", NETWORK_ADDR)
        self.socket.sendto(STANDARD_EVENT, NETWORK_ADDR)
        self.waitForLogLines(numLines1 + 1)

        self.assertEqual(self.numLinesLog(), numLines1 + 1) # only the canary was logged

    def lastLineCheck(self):
        with open(self.log_file, "r") as log:
            lastLine = log.read().splitlines()[-1]

        decodedJSON = json.loads(lastLine)

        self.assertEqual(decodedJSON["type"], "foo")
        self.assertEqual(decodedJSON["bar"], "baz")
        self.assertIn("_time", decodedJSON)

    def test_logMessageFormatted(self):
        numLines1 = self.numLinesLog()
        self.socket.sendto(STANDARD_EVENT, NETWORK_ADDR)
        self.waitForLogLines(numLines1 + 1)

        self.lastLineCheck()

    def test_messageDirectorLogging(self):
        numLines1 = self.numLinesLog()
        dg = Datagram.create_control()
        dg.add_uint16(CONTROL_LOG_MESSAGE)
        dg.add_blob(STANDARD_EVENT)

        self.mdsocket.send(dg)
        self.waitForLogLines(numLines1 + 1)

        self.lastLineCheck()


if __name__ == '__main__':
    unittest.main()
