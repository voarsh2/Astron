#!/usr/bin/env python3
import unittest, time, socket, os, json, tempfile
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

class TestEventLogger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logHandle, cls.log_file = tempfile.mkstemp(prefix = 'astron-', suffix = '.log')
        os.close(logHandle)

        cls.daemon = Daemon(CONFIG % cls.log_file)
        cls.daemon.start()

        cls.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        md_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        md_socket.connect(MD_ADDR)
        cls.mdsocket = MDConnection(md_socket)
        cls.waitForLogLines(1) # Wait for the EventLogger's startup event.

    @classmethod
    def tearDownClass(cls):
        cls.socket.close()
        cls.mdsocket.close()
        cls.daemon.stop()
        if cls.log_file is not None:
            os.remove(cls.log_file)

    @classmethod
    def numLinesLog(cls):
        with open(cls.log_file, "r") as log:
            return len(log.read().splitlines())

    @classmethod
    def waitForLogLines(cls, count):
        # The log file is the event logger's observable output. Poll for that
        # condition with a deadline; the polling interval is only a backoff.
        deadline = time.monotonic() + LOG_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            if cls.numLinesLog() >= count:
                return
            if cls.daemon.daemon.poll() is not None:
                raise RuntimeError("Astron exited before writing the expected event.")
            time.sleep(0.01)
        raise RuntimeError("Timed out waiting for the event logger output.")

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
