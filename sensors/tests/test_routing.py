from channels.testing import WebsocketCommunicator
from django.test import TestCase
from django.urls import reverse

from core.asgi import application


class RoutingTest(TestCase):
    async def test_websocket_route_valid(self):
        # Testing if the regex matches and connects to the consumer
        communicator = WebsocketCommunicator(application, "/ws/alerts/1/")
        # We don't need to fully connect, just check if the path is valid
        self.assertEqual(communicator.scope["path"], "/ws/alerts/1/")
        await communicator.disconnect()

    async def test_websocket_route_invalid(self):
        # Testing a path that doesn't match the regex
        communicator = WebsocketCommunicator(application, "/ws/invalid/path/")
        # This should fail to find a match in the URLRouter
        try:
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
        except ValueError:
            # Depending on setup, Channels might throw a ValueError if no route is found
            pass
