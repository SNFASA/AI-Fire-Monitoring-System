import json
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from ..models import Sensor
from .factories import HouselayoutFactory, SensorFactory, UserProfileFactory


class LiveSensorCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Users
        self.user_a = UserProfileFactory(role="public")
        self.user_b = UserProfileFactory(role="public")

        # 2. Setup initial data for User A
        self.layout_a = HouselayoutFactory(user=self.user_a.user, name="Main Floor")
        self.sensor_a = SensorFactory(
            owner=self.user_a, layout=self.layout_a, name="Kitchen"
        )

        self.live_url = reverse("sensors:live_data")
        self.add_url = reverse("sensors:add_sensor")
        self.move_url = reverse("sensors:update_sensor_pos")

    # --- get_live_data Tests ---

    def test_get_live_data_success(self):
        """Covers the main sensor list retrieval."""
        self.client.login(username=self.user_a.user.username, password="password123")
        response = self.client.get(self.live_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["sensors"]), 1)

    def test_get_live_data_exception(self):
        """Covers the 'except Exception as e' branch using a mock."""
        self.client.login(username=self.user_a.user.username, password="password123")
        with patch(
            "sensors.models.Sensor.objects.filter", side_effect=Exception("DB Down")
        ):
            response = self.client.get(self.live_url)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["error"], "Internal server error")

    # --- add_sensor Tests ---

    def test_add_sensor_success(self):
        """Covers valid sensor registration."""
        self.client.login(username=self.user_a.user.username, password="password123")
        payload = {"name": "Bedroom", "layout_id": self.layout_a.id}
        response = self.client.post(
            self.add_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.json()["success"], True)
        self.assertTrue(Sensor.objects.filter(name="Bedroom").exists())

    def test_add_sensor_validation_errors(self):
        """Covers missing name and missing layout_id branches."""
        self.client.login(username=self.user_a.user.username, password="password123")

        # Missing name
        response = self.client.post(
            self.add_url, json.dumps({"layout_id": 1}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Missing layout
        response = self.client.post(
            self.add_url, json.dumps({"name": "Test"}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_add_sensor_layout_ownership(self):
        """Covers Houselayout.DoesNotExist branch (adding to someone else's layout)."""
        self.client.login(username=self.user_b.user.username, password="password123")
        # User B tries to add a sensor to User A's layout
        payload = {"name": "Hacker Sensor", "layout_id": self.layout_a.id}
        response = self.client.post(
            self.add_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    # --- update_sensor_position Tests ---

    def test_update_position_success(self):
        """Covers valid X/Y position update."""
        self.client.login(username=self.user_a.user.username, password="password123")
        payload = {"sensor_id": self.sensor_a.id, "x": 50, "y": 75}
        response = self.client.post(
            self.move_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.json()["success"], True)
        self.sensor_a.refresh_from_db()
        self.assertEqual(self.sensor_a.x_position, 50)

    def test_update_position_access_denied(self):
        """Covers Sensor.DoesNotExist branch (moving someone else's sensor)."""
        self.client.login(username=self.user_b.user.username, password="password123")
        # User B tries to move User A's sensor
        payload = {"sensor_id": self.sensor_a.id, "x": 10, "y": 10}
        response = self.client.post(
            self.move_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["message"], "Sensor not found or access denied"
        )

    def test_invalid_json_payload(self):
        """Covers JSONDecodeError branch."""
        self.client.login(username=self.user_a.user.username, password="password123")
        response = self.client.post(
            self.add_url, "not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON payload.")
