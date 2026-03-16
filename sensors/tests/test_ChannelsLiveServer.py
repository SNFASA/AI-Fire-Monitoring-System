from channels.testing import WebsocketCommunicator
from core.asgi import application
from django.test import TransactionTestCase
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from .factories import UserFactory, UserProfileFactory, FireStationFactory


class ConsumerSecurityTest(TransactionTestCase):

    async def test_unauthenticated_connection_denied(self):
        """Covers: if not user.is_authenticated -> return False"""
        communicator = WebsocketCommunicator(application, "/ws/alerts/1/")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_wrong_station_access_denied(self):
        """Covers: str(user.userprofile.station.id) == str(station_id) -> False"""

        @database_sync_to_async
        def setup_data():
            # FIX: Manually force the station connection
            station = FireStationFactory()
            profile = UserProfileFactory(role="firefighter")
            profile.station = station
            profile.save()
            return profile.user

        user = await setup_data()
        station_b_id = 999  # Deliberately wrong station

        communicator = WebsocketCommunicator(application, f"/ws/alerts/{station_b_id}/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_missing_profile_exception(self):
        """Covers: the 'except Exception' block"""

        @database_sync_to_async
        def setup_deleted_profile():
            user = UserFactory()
            # Manually delete the profile to trigger the AttributeError in the consumer
            user.userprofile.delete()
            return user

        user = await setup_deleted_profile()

        communicator = WebsocketCommunicator(application, "/ws/alerts/1/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_successful_connection_and_alert(self):
        """Covers: The success path and the fire_alert method"""

        @database_sync_to_async
        def setup_valid_firefighter():
            station = FireStationFactory()
            profile = UserProfileFactory(role="firefighter")
            profile.station = station
            profile.save()
            return profile.user, profile.station.id

        user, station_id = await setup_valid_firefighter()

        communicator = WebsocketCommunicator(application, f"/ws/alerts/{station_id}/")
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # FIX: Simulate the Django View sending an alert to the Group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"station_{station_id}",  # The group name you defined in the consumer
            {
                "type": "fire_alert",  # This triggers your async def fire_alert()
                "report_id": 1,
                "address": "Test St",
                "owner_name": "Nabil",
                "owner_phone": "0123",
                "lat": 3.1,
                "lng": 101.1,
                "timestamp": "2026-03-16",
            },
        )

        # NOW the consumer will push the message down the WebSocket to our test client
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "fire_alert")
        self.assertEqual(response["owner_name"], "Nabil")

        await communicator.disconnect()
