#!/usr/bin/env python3
"""Regression coverage for Message Director queued writes and upstream setup."""

import os
import shutil
import socket
import tempfile
import time
import unittest
from pathlib import Path

from common.astron import (
    CONSTANTS,
    Daemon,
    Datagram,
    DatagramIterator,
    MDConnection,
)
from common.unittests import ProtocolTest


MD_PORT = 57123
UPSTREAM_MD_PORT = 57124
CHANNEL = 0x6F12AB34
WRITE_DATAGRAM_SIZE = Datagram.create([CHANNEL], 4321, 1337).get_size() + 1
WRITE_BUFFER_SIZE = WRITE_DATAGRAM_SIZE * 2 - 1

ACTIVE_WRITE_CONFIG = """\
messagedirector:
    bind: 127.0.0.1:%d
    threaded: false
    write_buffer_size: %d
""" % (MD_PORT, WRITE_BUFFER_SIZE)


def _release_gate(gate_directory):
    # Astron runs as a child process, so filesystem gates let a test pause an
    # async transition deterministically without relying on sleeps or socket
    # callback timing.
    temporary_file = os.path.join(gate_directory, "pending")
    release_file = os.path.join(gate_directory, "release-1")
    with open(temporary_file, "w", encoding="utf-8") as release:
        release.write("release\n")
    os.replace(temporary_file, release_file)


class TestMessageDirectorWriteQueue(ProtocolTest):
    @classmethod
    def setUpClass(cls):
        cls.write_gate_directory = tempfile.mkdtemp(prefix="astron-write-gate-")
        cls.addClassCleanup(shutil.rmtree, cls.write_gate_directory, True)
        cls.daemon = Daemon(ACTIVE_WRITE_CONFIG)
        cls.addClassCleanup(cls.daemon.stop)

        previous = os.environ.get("ASTRON_TEST_NETWORK_WRITE_RELEASE_DIRECTORY")
        os.environ["ASTRON_TEST_NETWORK_WRITE_RELEASE_DIRECTORY"] = cls.write_gate_directory
        try:
            cls.daemon.start()
        finally:
            if previous is None:
                os.environ.pop("ASTRON_TEST_NETWORK_WRITE_RELEASE_DIRECTORY", None)
            else:
                os.environ["ASTRON_TEST_NETWORK_WRITE_RELEASE_DIRECTORY"] = previous

        cls.source = cls.connectToServer(port=MD_PORT)
        cls.addClassCleanup(cls.source.close)
        cls.slow_peer = cls.connectToServer(port=MD_PORT)
        cls.addClassCleanup(cls.slow_peer.close)

        position = cls.daemon.output_position()
        cls.slow_peer.send(Datagram.create_add_channel(CHANNEL))
        cls.daemon.wait_for_output(
            "ASTRON_TEST_CHANNEL_SUBSCRIBED:%d" % CHANNEL,
            after=position,
        )

    def assertConnectionClosed(self, conn):
        deadline = time.monotonic() + 5
        timeout = conn.s.gettimeout()
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                conn.s.settimeout(min(0.1, remaining))
                try:
                    datagram = conn.recv_maybe()
                except EOFError:
                    return
                if datagram is not None:
                    self.fail("Received an unexpected datagram before connection close")
            self.fail("Message Director did not close the over-limit connection")
        finally:
            conn.s.settimeout(timeout)

    def test_active_write_counts_toward_limit(self):
        first = Datagram.create([CHANNEL], 4321, 1337)
        first.add_uint8(0x51)
        second = Datagram.create([CHANNEL], 4321, 1337)
        second.add_uint8(0x52)
        self.assertLessEqual(first.get_size(), WRITE_BUFFER_SIZE)
        self.assertLessEqual(second.get_size(), WRITE_BUFFER_SIZE)
        self.assertGreater(first.get_size() + second.get_size(), WRITE_BUFFER_SIZE)

        Path(self.write_gate_directory, "arm").touch()
        self.source.send(first)
        self.expect(self.slow_peer, first)
        self.daemon.wait_for_output("ASTRON_TEST_NETWORK_WRITE_GATE_READY")

        overflow_position = self.daemon.output_position()
        self.source.send(second)
        self.daemon.wait_for_output(
            "ASTRON_TEST_WRITE_BUFFER_OVERFLOW", after=overflow_position
        )

        # This empty frame fits exactly in the remaining quota after the
        # in-flight write. It must still be dropped because disconnect has
        # already started. The following control message is an observable
        # barrier proving the routed frame was processed before releasing the
        # write callback.
        follow_up = Datagram.create([CHANNEL], 4321, 1337)
        self.assertEqual(follow_up.get_size(), WRITE_BUFFER_SIZE - first.get_size())
        self.source.send(follow_up)
        barrier_channel = CHANNEL + 1
        position = self.daemon.output_position()
        self.source.send(Datagram.create_add_channel(barrier_channel))
        self.daemon.wait_for_output(
            "ASTRON_TEST_CHANNEL_SUBSCRIBED:%d" % barrier_channel,
            after=position,
        )

        # Hold the write-completion callback until the second datagram has been
        # rejected. This keeps the first payload accounted as in flight without
        # relying on TCP coalescing or the OS callback schedule.
        _release_gate(self.write_gate_directory)
        self.daemon.wait_for_output("ASTRON_TEST_NETWORK_WRITE_GATE_RESUMED")
        self.assertConnectionClosed(self.slow_peer)


class _UpstreamQueueTestBase(ProtocolTest):
    write_buffer_size = 0
    threaded_mode = True

    def setUp(self):
        self.gate_directory = tempfile.mkdtemp(prefix="astron-upstream-gate-")
        self.drain_gate_directory = tempfile.mkdtemp(prefix="astron-upstream-drain-gate-")
        self.addCleanup(self._cleanup)

        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(5)
        upstream_port = self.listener.getsockname()[1]

        config = """\
messagedirector:
    bind: 127.0.0.1:%d
    connect: 127.0.0.1:%d
    threaded: %s
    write_buffer_size: %d
""" % (UPSTREAM_MD_PORT, upstream_port, str(self.threaded_mode).lower(),
       self.write_buffer_size)
        gate_variables = {
            "ASTRON_TEST_UPSTREAM_READY_RELEASE_DIRECTORY": self.gate_directory,
            "ASTRON_TEST_UPSTREAM_DRAIN_RELEASE_DIRECTORY": self.drain_gate_directory,
        }
        previous_values = {key: os.environ.get(key) for key in gate_variables}
        os.environ.update(gate_variables)
        try:
            self.daemon = Daemon(config)
            self.daemon.start()
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.daemon.wait_for_output("ASTRON_TEST_UPSTREAM_READY_GATE_READY")

        self.upstream_socket, _ = self.listener.accept()
        self.upstream_socket.settimeout(5)
        self.upstream = MDConnection(self.upstream_socket)
        self.upstream.s.settimeout(5)
        self.source = self.connectToServer(port=UPSTREAM_MD_PORT)

    def _cleanup(self):
        for gate_directory in (getattr(self, "gate_directory", None),
                               getattr(self, "drain_gate_directory", None)):
            if gate_directory and os.path.isdir(gate_directory):
                release_file = os.path.join(gate_directory, "release-1")
                if not os.path.exists(release_file):
                    _release_gate(gate_directory)
        if hasattr(self, "daemon"):
            self.daemon.stop()
        if hasattr(self, "source"):
            self.source.close()
        if hasattr(self, "upstream_socket"):
            self.upstream_socket.close()
        if hasattr(self, "listener"):
            self.listener.close()
        if os.path.isdir(self.gate_directory):
            shutil.rmtree(self.gate_directory)
        if os.path.isdir(self.drain_gate_directory):
            shutil.rmtree(self.drain_gate_directory)

    def subscribe(self, channel):
        position = self.daemon.output_position()
        self.source.send(Datagram.create_add_channel(channel))
        self.daemon.wait_for_output(
            "ASTRON_TEST_CHANNEL_SUBSCRIBED:%d" % channel,
            after=position,
        )

    def assert_upstream_add_channel(self, channel):
        datagram = self.upstream.recv()
        iterator = DatagramIterator(datagram)
        self.assertEqual(iterator.read_uint8(), 1)
        self.assertEqual(iterator.read_channel(), CONSTANTS["CONTROL_CHANNEL"])
        self.assertEqual(iterator.read_uint16(), CONSTANTS["CONTROL_ADD_CHANNEL"])
        self.assertEqual(iterator.read_channel(), channel)
        self.assertEqual(iterator.tell(), datagram.get_size())


class TestMessageDirectorUpstreamQueueFlush(_UpstreamQueueTestBase):
    write_buffer_size = 256

    def test_staged_and_transition_datagrams_reach_upstream(self):
        channels = (0x6F12AB35, 0x6F12AB36)
        for channel in channels:
            self.subscribe(channel)

        _release_gate(self.gate_directory)
        self.daemon.wait_for_output("ASTRON_TEST_UPSTREAM_DRAIN_GATE_READY")

        # A routed data frame reaches send_datagram on the routing thread while
        # the connection callback holds the queue lock for the staged drain.
        payload = Datagram.create([0x6F12AB37], 4321, 1337)
        payload.add_uint8(0xA5)
        position = self.daemon.output_position()
        self.source.send(payload)
        self.daemon.wait_for_output(
            "ASTRON_TEST_UPSTREAM_SEND_LOCK_BLOCKED", after=position
        )
        _release_gate(self.drain_gate_directory)
        self.daemon.wait_for_output("ASTRON_TEST_UPSTREAM_DRAIN_GATE_RESUMED")

        self.assert_upstream_add_channel(channels[0])
        self.assert_upstream_add_channel(channels[1])
        self.assertEqual(self.upstream.recv().get_data(), payload.get_data())


class TestMessageDirectorUpstreamQueueLimit(_UpstreamQueueTestBase):
    routed_datagram_size = Datagram.create([1], 1, 1).get_size() + 1
    write_buffer_size = routed_datagram_size * 2 + routed_datagram_size // 2
    threaded_mode = False

    def test_preconnect_queue_is_bounded(self):
        overflow_position = self.daemon.output_position()
        for channel in (0x6F12AB38, 0x6F12AB39, 0x6F12AB3A):
            payload = Datagram.create([channel], 4321, 1337)
            payload.add_uint8(0xA5)
            self.source.send(payload)
        self.daemon.wait_for_output(
            "ASTRON_TEST_WRITE_BUFFER_OVERFLOW", after=overflow_position
        )
        self.assertEqual(self.daemon.daemon.wait(timeout=5), 1)


if __name__ == "__main__":
    unittest.main()
