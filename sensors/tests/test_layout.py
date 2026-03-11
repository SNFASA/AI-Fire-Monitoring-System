import json
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from sensors.models import Sensor, Houselayout
from .factories import UserProfileFactory, SensorFactory


class LayoutAndSensorTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Create User & Profile via Factory
        # The factory automatically sets password to 'password123'
        self.profile = UserProfileFactory(role="public")
        self.user = self.profile.user

        self.client.login(username=self.user.username, password="password123")

        # 2. URLs
        self.upload_url = reverse("sensors:upload_layout")
        self.add_sensor_url = reverse("sensors:add_sensor")
        self.update_pos_url = reverse("sensors:update_sensor_pos")

    def test_upload_layout_success(self):
        """TC-001: Test uploading multiple layouts"""
        image_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"

        file1 = SimpleUploadedFile(
            "layout1.gif", image_content, content_type="image/gif"
        )
        self.client.post(self.upload_url, {"name": "Ground Floor", "image": file1})

        file2 = SimpleUploadedFile(
            "layout2.gif", image_content, content_type="image/gif"
        )
        self.client.post(self.upload_url, {"name": "Second Floor", "image": file2})

        layouts = Houselayout.objects.filter(user=self.user)
        self.assertEqual(layouts.count(), 2)

    def test_add_sensor_api(self):
        """TC-002: Test adding a sensor linked to a specific layout"""
        layout = Houselayout.objects.create(
            user=self.user, name="Test Layout", image="test.jpg"
        )

        data = {"name": "Living Room Sensor", "layout_id": layout.id}

        response = self.client.post(
            self.add_sensor_url, data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        sensor = Sensor.objects.filter(
            owner=self.profile, name="Living Room Sensor"
        ).first()
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor.layout, layout)

    def test_update_sensor_position(self):
        """TC-003: Test updating X/Y coordinates of a sensor"""
        # Create sensor using factory
        sensor = SensorFactory(
            owner=self.profile, name="Moveable Sensor", x_position=10, y_position=10
        )

        new_pos = {"sensor_id": sensor.id, "x": 55.5, "y": 80.2}

        response = self.client.post(
            self.update_pos_url,
            data=json.dumps(new_pos),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        sensor.refresh_from_db()
        self.assertEqual(sensor.x_position, 55.5)

    def test_cannot_update_others_sensor(self):
        """TC-004: Security Check - Ensure user cannot move another user's sensor"""
        victim_sensor = SensorFactory(owner=self.profile, x_position=10)

        # Create Hacker
        hacker_profile = UserProfileFactory(user__username="hacker")

        self.client.logout()
        self.client.login(username="hacker", password="password123")

        payload = {"sensor_id": victim_sensor.id, "x": 0, "y": 0}

        response = self.client.post(
            self.update_pos_url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertFalse(response.json()["success"])
        victim_sensor.refresh_from_db()
        self.assertEqual(victim_sensor.x_position, 10)
