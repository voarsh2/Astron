#!/usr/bin/env python3
"""Deterministic regression for stale Client::m_pending_objects contexts."""

import unittest
import os
from socket import AF_INET, SOCK_STREAM, socket

from common.astron import *
from common.dcfile import *
from common.unittests import ProtocolTest


MD_PORT = 57123
# Keep this fixed listener below common ephemeral-port ranges to avoid
# collisions with local ports left in TIME_WAIT by earlier test connections.
CLIENTAGENT_PORT = 27128
PARENT = 1234
ZONE = 4321
OBJECT = 8888
BARRIER_CHANNEL = 0x6F12AB34

CONFIG = """\
messagedirector:
    bind: 127.0.0.1:%d
    threaded: %s

general:
    dc_files:
        - %r

uberdogs:
    - id: 1234
      class: UberDog1
      anonymous: true

roles:
    - type: clientagent
      bind: 127.0.0.1:%d
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
""" % (MD_PORT, USE_THREADING, test_dc, CLIENTAGENT_PORT)


@unittest.skipIf('MANUAL_LAUNCH_CONFIG' in os.environ,
                 'pending-object setup requires test daemon output')
class TestPendingObjectContext(ProtocolTest):
    @classmethod
    def setUpClass(cls):
        cls.daemon = Daemon(CONFIG)
        cls.addClassCleanup(cls.daemon.stop)
        cls.daemon.start()
        cls.server = cls.connectToServer(port=MD_PORT)
        cls.addClassCleanup(cls.server.close)
        position = cls.daemon.output_position()
        cls.server.send(Datagram.create_add_channel(1234))
        cls.server.send(Datagram.create_add_channel(BARRIER_CHANNEL))
        cls.daemon.wait_for_output(
            'ASTRON_TEST_CHANNEL_SUBSCRIBED:%d' % BARRIER_CHANNEL,
            after=position,
        )

    def connect_client(self):
        client_socket = socket(AF_INET, SOCK_STREAM)
        client_socket.connect(("127.0.0.1", CLIENTAGENT_PORT))
        client = ClientConnection(client_socket)

        hello = Datagram()
        hello.add_uint16(CLIENT_HELLO)
        hello.add_uint32(DC_HASH)
        hello.add_string("Sword Art Online v5.1")
        client.send(hello)
        hello_response = Datagram()
        hello_response.add_uint16(CLIENT_HELLO_RESP)
        self.expect(client, hello_response, isClient=True)
        return client

    def identify(self, client):
        identify = Datagram()
        identify.add_uint16(CLIENT_OBJECT_SET_FIELD)
        identify.add_doid(1234)
        identify.add_uint16(request)
        identify.add_string("identify pending-object test client")
        client.send(identify)

        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "UberDOG did not receive the identify request")
        dgi = DatagramIterator(response)
        self.assertEqual(dgi.read_uint8(), 1)
        self.assertEqual(dgi.read_channel(), 1234)
        client_id = dgi.read_channel()
        self.assertEqual(dgi.read_uint16(), STATESERVER_OBJECT_SET_FIELD)
        return client_id

    def synchronize_clientagent(self, client_id, context):
        request = Datagram.create(
            [client_id], 1234, CLIENTAGENT_GET_NETWORK_ADDRESS
        )
        request.add_uint32(context)
        self.server.send(request)

        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "ClientAgent synchronization response was missing")
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [1234], client_id, CLIENTAGENT_GET_NETWORK_ADDRESS_RESP
        ))
        self.assertEqual(dgi.read_uint32(), context)

    def add_interest(self, client, client_id, interest_id, client_context):
        request = Datagram()
        request.add_uint16(CLIENT_ADD_INTEREST)
        request.add_uint32(client_context)
        request.add_uint16(interest_id)
        request.add_doid(PARENT)
        request.add_zone(ZONE)
        client.send(request)

        response = self.recv_expected(self.server)
        self.assertIsNotNone(response, "ClientAgent did not query the State Server")
        dgi = DatagramIterator(response)
        self.assertTrue(*dgi.matches_header(
            [PARENT], client_id, STATESERVER_OBJECT_GET_ZONES_OBJECTS
        ))
        request_context = dgi.read_uint32()
        self.assertEqual(dgi.read_doid(), PARENT)
        self.assertEqual(dgi.read_uint16(), 1)
        self.assertEqual(dgi.read_zone(), ZONE)
        return request_context

    def expect_client_message(self, client, message_type, context, interest_id):
        response = self.recv_expected(client)
        self.assertIsNotNone(response, "ClientAgent did not send the expected interest response")
        dgi = DatagramIterator(response)
        self.assertEqual(dgi.read_uint16(), message_type)
        self.assertEqual(dgi.read_uint32(), context)
        self.assertEqual(dgi.read_uint16(), interest_id)

    def test_pending_location_requeued_into_new_interest(self):
        client = self.connect_client()
        try:
            client_id = self.identify(client)

            state = Datagram.create([client_id], 1, CLIENTAGENT_SET_STATE)
            state.add_uint16(CLIENT_STATE_ESTABLISHED)
            self.server.send(state)
            self.synchronize_clientagent(client_id, 3000)

            # R1 stays pending because no GET_ZONES_COUNT_RESP is sent yet.
            first_context = self.add_interest(client, client_id, 1, 2000)

            location = Datagram.create(
                [client_id], 1, STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED
            )
            location.add_doid(OBJECT)
            location.add_doid(PARENT)
            location.add_zone(ZONE)
            location.add_uint16(DistributedTestObject1)
            location.add_uint32(999999)
            self.server.send(location)
            self.synchronize_clientagent(client_id, 3001)

            # Removing the visible interest does not finish its pending IOP.
            remove = Datagram()
            remove.add_uint16(CLIENT_REMOVE_INTEREST)
            remove.add_uint32(2001)
            remove.add_uint16(1)
            client.send(remove)
            self.expect_client_message(client, CLIENT_DONE_INTEREST_RESP, 2001, 1)

            # R2 opens the same zone while R1 still owns the buffered location.
            second_context = self.add_interest(client, client_id, 2, 2002)
            self.assertNotEqual(first_context, second_context)

            # R1 completes and redispatches its queued location into R2. The
            # object-to-context association must now name R2, not erased R1.
            first_count = Datagram.create(
                [client_id], 1234, STATESERVER_OBJECT_GET_ZONES_COUNT_RESP
            )
            first_count.add_uint32(first_context)
            first_count.add_doid(0)
            self.server.send(first_count)
            self.expect_client_message(client, CLIENT_DONE_INTEREST_RESP, 2000, 1)

            # A subsequent message for the pending object used to dereference
            # end() in try_queue_pending. Synchronize on the same MD connection
            # so the assertion proves the ClientAgent processed it.
            changing_location = Datagram.create(
                [client_id], 1, STATESERVER_OBJECT_CHANGING_LOCATION
            )
            changing_location.add_doid(OBJECT)
            changing_location.add_doid(PARENT)
            changing_location.add_zone(ZONE + 1)
            changing_location.add_doid(PARENT)
            changing_location.add_zone(ZONE)
            self.server.send(changing_location)
            self.synchronize_clientagent(client_id, 3002)

            # Finish R2 and verify both queued messages are delivered in order.
            second_count = Datagram.create(
                [client_id], 1234, STATESERVER_OBJECT_GET_ZONES_COUNT_RESP
            )
            second_count.add_uint32(second_context)
            second_count.add_doid(0)
            self.server.send(second_count)

            self.expect_client_message(client, CLIENT_DONE_INTEREST_RESP, 2002, 2)
            entered = Datagram()
            entered.add_uint16(CLIENT_ENTER_OBJECT_REQUIRED)
            entered.add_doid(OBJECT)
            entered.add_doid(PARENT)
            entered.add_zone(ZONE)
            entered.add_uint16(DistributedTestObject1)
            entered.add_uint32(999999)
            self.expect(client, entered, isClient=True)

            left = Datagram()
            left.add_uint16(CLIENT_OBJECT_LEAVING)
            left.add_doid(OBJECT)
            self.expect(client, left, isClient=True)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
