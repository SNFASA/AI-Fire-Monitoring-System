from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from sensors.models import Report, DutyAssignment, Sensor
import json
from unittest.mock import patch
from .factories import UserProfileFactory, FireStationFactory, AddressFactory


class AlertSystemTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Use the namespace as the primary URL lookup
        try:
            self.url = reverse("sensors:receive_data")
        except NoReverseMatch:
            self.url = reverse("receive_data")

        # 1. Create explicit Address with float coordinates
        self.owner_addr = AddressFactory(latitude=3.1390, longitude=101.6869)

        # 2. CRITICAL FIX: Explicitly assign address to bypass post_save signal interference
        self.owner_profile = UserProfileFactory()
        self.owner_profile.role = "public"
        self.owner_profile.address = self.owner_addr
        self.owner_profile.save()

        # 3. Create Sensor linked to this owner
        self.sensor = Sensor.objects.create(
            owner=self.owner_profile, name="Kitchen Sensor", is_active=True
        )

        # 4. Create Station with valid coordinates
        self.station_addr = AddressFactory(latitude=3.1400, longitude=101.6900)
        self.station = FireStationFactory(address=self.station_addr)

        # 5. CRITICAL FIX: Explicitly assign station and role to bypass signal interference
        self.ff = UserProfileFactory()
        self.ff.role = "firefighter"
        self.ff.station = self.station
        self.ff.save()

        DutyAssignment.objects.create(
            firefighter=self.ff,
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            is_active=True,
        )

    @patch("sensors.views.api.async_to_sync")
    @patch("sensors.views.api.predictor.predict")
    @patch("sensors.views.api.send_sms_broadcast")
    @patch("sensors.views.api.get_channel_layer")
    @patch("sensors.views.api.haversine")
    def test_fire_detected_scenario(
        self, mock_hav, mock_channel, mock_sms, mock_predict, mock_async
    ):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 0.5
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        # Full payload to satisfy SensorDataLog model requirements
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800,
            "lpg": 700,
            "co": 300,
            "air_quality": 500,
            "dht22_temp": 65.5,
            "humidity": 20,
            "flame_val": 100,
        }

        # Clear reports before the test to be 100% sure of count
        Report.objects.all().delete()

        response = self.client.post(
            self.url, json.dumps(payload), content_type="application/json"
        )

        # Debug print in case it fails again in CI
        if Report.objects.count() == 0:
            print(f"DEBUG: Response Content: {response.content.decode()}")

        self.assertEqual(
            Report.objects.count(),
            1,
            "Report should be created when a valid address exists",
        )

    @patch("sensors.views.api.predictor.predict")
    def test_safe_scenario(self, mock_predict):
        mock_predict.return_value = "Safe"
        # Even safe scenarios should send full logs to avoid database integrity errors
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 100,
            "lpg": 100,
            "co": 20,
            "air_quality": 30,
            "dht22_temp": 28.0,
            "humidity": 60.0,
            "flame_val": 4095,
        }
        response = self.client.post(
            self.url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.content.decode(), "0")
        self.assertEqual(Report.objects.count(), 0)

    @patch("sensors.views.api.haversine")
    @patch("sensors.views.api.predictor.predict")
    def test_deduplication_logic(self, mock_predict, mock_hav):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 1.0

        # Create initial report using the valid explicitly-saved address
        Report.objects.create(
            status="System Detected",
            address=self.owner_addr,
            station=self.station,
            trigger_sensor=self.sensor,
        )

        # Updated with complete payload
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 850,
            "lpg": 750,
            "co": 350,
            "air_quality": 550,
            "dht22_temp": 90.0,
            "humidity": 15.0,
            "flame_val": 80,
        }
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Count should remain 1 (updated existing report instead of creating a new one)
        self.assertEqual(Report.objects.count(), 1)

    @patch("sensors.views.api.haversine")
    @patch("sensors.views.api.predictor.predict")
    @patch("sensors.views.api.async_to_sync")
    def test_no_active_staff_fallback(self, mock_async, mock_predict, mock_hav):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 5.0
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        # Clear all duties to trigger fallback logic
        DutyAssignment.objects.all().delete()

        # Updated with complete payload
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 900,
            "lpg": 800,
            "co": 400,
            "air_quality": 600,
            "dht22_temp": 95.0,
            "humidity": 10.0,
            "flame_val": 50,
        }
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Fallback should correctly assign to nearest station even if no staff are on duty
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.first().station, self.station)

    def test_invalid_sensor_id(self):
        payload = {"sensor_id": 999999}
        response = self.client.post(
            self.url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.content.decode(), "0")

    def test_invalid_method_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
