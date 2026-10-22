#!/usr/bin/env python3
"""Regression reproducer for issue #427's fast server-side interest path."""

import time
import unittest
import os
import tempfile
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket

from common.astron import *
from common.dcfile import *
from common.unittests import ProtocolTest


CONFIG = """\
messagedirector:
    bind: 127.0.0.1:57123
    threaded: %s

general:
    dc_files:
        - %r

uberdogs:
    - id: 1234
      class: UberDog1
      anonymous: true

roles:
    - type: stateserver
      control: 100100

    - type: clientagent
      bind: 127.0.0.1:57128
      version: "Sword Art Online v5.1"
      channels:
          min: 3100
          max: 3999
      client:
          add_interest: enabled
          write_buffer_size: 0
          write_timeout_ms: 0
      tuning:
          interest_timeout: 10000
""" % (USE_THREADING, test_dc)


class TestIssue427(ProtocolTest):
    @classmethod
    def setUpClass(cls):
        # The test-only build hook defers timeout setup without blocking the
        # main loop, making it possible to exercise completion and disconnect
        # before the setup callback runs.
        marker_fd, cls.timeout_setup_marker = tempfile.mkstemp(
            prefix="astron-issue-427-resumed-"
        )
        os.close(marker_fd)
        release_fd, cls.timeout_setup_release = tempfile.mkstemp(
            prefix="astron-issue-427-release-"
        )
        os.close(release_fd)
        os.unlink(cls.timeout_setup_release)

        previous_delay = os.environ.get("ASTRON_TEST_DELAY_INTEREST_TIMEOUT_SETUP_MS")
        previous_marker = os.environ.get(
            "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED_FILE"
        )
        previous_release = os.environ.get(
            "ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE"
        )
        os.environ["ASTRON_TEST_DELAY_INTEREST_TIMEOUT_SETUP_MS"] = "1000"
        os.environ["ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED_FILE"] = (
            cls.timeout_setup_marker
        )
        os.environ["ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE"] = (
            cls.timeout_setup_release
        )
        cls.daemon = Daemon(CONFIG)
        try:
            cls.daemon.start()
        finally:
            if previous_delay is None:
                os.environ.pop("ASTRON_TEST_DELAY_INTEREST_TIMEOUT_SETUP_MS", None)
            else:
                os.environ["ASTRON_TEST_DELAY_INTEREST_TIMEOUT_SETUP_MS"] = previous_delay
            if previous_marker is None:
                os.environ.pop("ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED_FILE", None)
            else:
                os.environ["ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RESUMED_FILE"] = (
                    previous_marker
                )
            if previous_release is None:
                os.environ.pop("ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE", None)
            else:
                os.environ["ASTRON_TEST_INTEREST_TIMEOUT_SETUP_RELEASE_FILE"] = (
                    previous_release
                )
        cls.server = cls.connectToServer()
        for channel in (5, 1015, 1234):
            cls.server.send(Datagram.create_add_channel(channel))

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.daemon.stop()
        os.unlink(cls.timeout_setup_marker)
        if os.path.exists(cls.timeout_setup_release):
            os.unlink(cls.timeout_setup_release)

    def reset_timeout_setup_marker(self):
        Path(self.timeout_setup_marker).write_text("", encoding="utf-8")
        if os.path.exists(self.timeout_setup_release):
            os.unlink(self.timeout_setup_release)

    def release_timeout_setup(self):
        Path(self.timeout_setup_release).touch()

    def wait_for_timeout_setup_resume(self):
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if "resumed\n" in Path(self.timeout_setup_marker).read_text(
                encoding="utf-8"
            ):
                return
            if self.daemon.daemon.poll() is not None:
                self.fail("Astron exited before deferred timeout setup resumed.")
            time.sleep(0.01)
        self.fail("Deferred timeout setup callback did not resume.")

    def connect(self):
        client_socket = socket(AF_INET, SOCK_STREAM)
        client_socket.connect(("127.0.0.1", 57128))
        client = ClientConnection(client_socket)

        hello = Datagram()
        hello.add_uint16(CLIENT_HELLO)
        hello.add_uint32(DC_HASH)
        hello.add_string("Sword Art Online v5.1")
        client.send(hello)

        response = Datagram()
        response.add_uint16(CLIENT_HELLO_RESP)
        self.expect(client, response, isClient=True)
        return client

    def identify(self, client):
        dg = Datagram()
        dg.add_uint16(CLIENT_OBJECT_SET_FIELD)
        dg.add_doid(1234)
        dg.add_uint16(request)
        dg.add_string("issue-427")
        client.send(dg)

        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "No identify datagram arrived at the UberDOG.")
        dgi = DatagramIterator(response)
        self.assertEqual(dgi.read_uint8(), 1)
        self.assertEqual(dgi.read_channel(), 1234)
        client_id = dgi.read_channel()
        self.assertGreaterEqual(client_id, 3100)
        self.assertLessEqual(client_id, 3999)
        return client_id

    def create_empty_parent(self, parent_id, context):
        create_parent = Datagram.create(
            [100100], 5, STATESERVER_CREATE_OBJECT_WITH_REQUIRED
        )
        create_parent.add_doid(parent_id)
        create_parent.add_doid(0)
        create_parent.add_zone(0)
        create_parent.add_uint16(DistributedTestObject1)
        create_parent.add_uint32(0)
        self.server.send(create_parent)

        # Confirm the State Server registered it before testing its snapshot.
        readiness_query = Datagram.create(
            [parent_id], 5, STATESERVER_OBJECT_GET_ZONES_OBJECTS
        )
        readiness_query.add_uint32(context)
        readiness_query.add_doid(parent_id)
        readiness_query.add_uint16(1)
        readiness_query.add_zone(20000)
        self.server.send(readiness_query)
        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "State Server parent did not become active.")
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [5], parent_id, STATESERVER_OBJECT_GET_ZONES_COUNT_RESP
        ))
        self.assertEqual(dgi.read_uint32(), context)
        self.assertEqual(dgi.read_doid(), 0)

    def query_empty_parent(self, parent_id, context):
        query = Datagram.create(
            [parent_id], 5, STATESERVER_OBJECT_GET_ZONES_OBJECTS
        )
        query.add_uint32(context)
        query.add_doid(parent_id)
        query.add_uint16(1)
        query.add_zone(20000)
        self.server.send(query)
        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "State Server stopped answering queries.")
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [5], parent_id, STATESERVER_OBJECT_GET_ZONES_COUNT_RESP
        ))
        self.assertEqual(dgi.read_uint32(), context)
        self.assertEqual(dgi.read_doid(), 0)

    def test_fast_state_server_snapshot_does_not_leave_a_dangling_timeout(self):
        # The parent object answers GET_ZONES_OBJECTS inside this daemon. Empty
        # snapshots complete the interest as soon as the count response arrives.
        parent_id = 500000
        self.create_empty_parent(parent_id, 427)

        client = self.connect()
        client_id = self.identify(client)
        set_state = Datagram.create([client_id], 1, CLIENTAGENT_SET_STATE)
        set_state.add_uint16(CLIENT_STATE_ESTABLISHED)
        self.server.send(set_state)

        # One operation is enough: the delayed main-loop task gives the
        # threaded Message Director time to finish this empty snapshot first.
        add_interest = Datagram.create(
            [client_id], 1015, CLIENTAGENT_ADD_INTEREST
        )
        add_interest.add_uint16(1)
        add_interest.add_doid(parent_id)
        add_interest.add_zone(30000)
        self.reset_timeout_setup_marker()
        self.server.send(add_interest)

        response = self.recv_expected(self.server)
        self.assertIsNotNone(
            response, "Timed out waiting for server-side interest completion."
        )
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [1015], client_id, CLIENTAGENT_DONE_INTEREST_RESP
        ))
        self.assertEqual(dgi.read_channel(), client_id)
        dgi.read_uint16() # Interest id

        # Only now release the deferred continuation. Observe it return, then
        # prove the daemon survived and can still answer a State Server request.
        self.release_timeout_setup()
        self.wait_for_timeout_setup_resume()
        self.assertIsNone(self.daemon.daemon.poll(), "Astron crashed after the interest completed.")
        self.query_empty_parent(parent_id, 428)

        client.close()

    def test_disconnect_before_timeout_setup_does_not_leave_client_callback(self):
        parent_id = 500001
        self.create_empty_parent(parent_id, 429)

        client = self.connect()
        client_id = self.identify(client)
        set_state = Datagram.create([client_id], 1, CLIENTAGENT_SET_STATE)
        set_state.add_uint16(CLIENT_STATE_ESTABLISHED)
        self.server.send(set_state)

        # No State Server owns this parent, so the operation remains pending.
        # The test hook lets the client disconnect and be removed before the
        # deferred timeout-setup callback resumes.
        add_interest = Datagram.create(
            [client_id], 1015, CLIENTAGENT_ADD_INTEREST
        )
        add_interest.add_uint16(2)
        add_interest.add_doid(600000)
        add_interest.add_zone(30001)
        self.reset_timeout_setup_marker()
        self.server.send(add_interest)

        client_interest = self.recv_expected(client)
        self.assertIsNotNone(client_interest, "ClientAgent did not forward the interest.")
        client_dgi = DatagramIterator(client_interest)
        self.assertEqual(client_dgi.read_uint16(), CLIENT_ADD_INTEREST)
        client.close()

        # Client::annihilate completes pending interests and reports completion
        # to the server caller while removing the Client from the Message Director.
        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "Disconnect did not finish its pending interest.")
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [1015], client_id, CLIENTAGENT_DONE_INTEREST_RESP
        ))

        # Give the Message Director a routed message so it drains its deferred
        # participant deletion before the delayed setup event fires.
        self.query_empty_parent(parent_id, 430)

        # The disconnect completion response proves finish() removed the
        # pending operation. Release its continuation only after that response.
        self.release_timeout_setup()

        # Confirm the deferred setup callback resumed after disconnect; it must
        # not dereference the Client or operation after removal.
        self.wait_for_timeout_setup_resume()
        self.assertIsNone(self.daemon.daemon.poll(), "Astron crashed after client disconnect.")
        self.query_empty_parent(parent_id, 431)


if __name__ == "__main__":
    unittest.main()
