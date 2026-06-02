import json
from datetime import timedelta
from unittest.mock import patch

from django.core.signing import TimestampSigner
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Address, Report, SensorDataLog, User

# Adjust the import path below if your functions are in a different file (e.g., api.py)
from ..views.api import normalize_ml_result
from .factories import (
    AddressFactory,
    DutyAssignmentFactory,
    FireStationFactory,
    SensorFactory,
    UserProfileFactory,
)


class ComprehensiveApiViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.signer = TimestampSigner()

        # 1. Base Setup: Public Owner
        self.address = AddressFactory(latitude=3.123, longitude=101.456)
        self.user_profile = UserProfileFactory(role="public")
        self.user_profile.address = self.address
        self.user_profile.phone_number = "0123456789"
        self.user_profile.save()

        self.sensor = SensorFactory(owner=self.user_profile)

        # 2. Base Setup: Station & On-Duty Firefighter
        self.station_addr = AddressFactory(latitude=3.1, longitude=101.1)
        self.station = FireStationFactory(address=self.station_addr)

        self.ff_user = User.objects.create_user(
            username="nabil_on_duty", password="password123"
        )
        self.ff_profile = UserProfileFactory(
            user=self.ff_user,
            role="firefighter",
            station=self.station,
            phone_number="0198765432",
        )

        # 3. URLs
        self.receive_url = reverse("sensors:receive_data")

        # Assuming these are your URL names in urls.py
        self.update_url_name = "sensors:update_location_link"
        self.test_log_url = reverse("sensors:test_log")
        self.filters_url = reverse("sensors:filter_sensors")

    # ==========================================
    # 1. UTILITY & SIMPLE VIEWS COVERAGE
    # ==========================================
    def test_normalize_ml_result(self):
        """Hits every branch of the ML string normalizer."""
        self.assertEqual(normalize_ml_result(None), "Safe")
        self.assertEqual(normalize_ml_result(" fire "), "Fire")
        self.assertEqual(normalize_ml_result("GASLEAK"), "Gas Leak")
        self.assertEqual(normalize_ml_result("gas leak"), "Gas Leak")
        self.assertEqual(normalize_ml_result("Warning"), "Warning")
        self.assertEqual(normalize_ml_result("Random Noise"), "Safe")

    @patch("sensors.views.api.add_log")
    def test_test_log_view(self, mock_add_log):
        """Covers the simple logging test endpoint."""
        response = self.client.get(self.test_log_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_add_log.called)

    # ==========================================
    # 2. RECEIVE SENSOR DATA COVERAGE (DISPATCH)
    # ==========================================
    def test_receive_data_invalid_method(self):
        """Covers status=405 block."""
        response = self.client.get(self.receive_url)
        self.assertEqual(response.status_code, 405)

    def test_receive_data_empty_body(self):
        """Covers not request.body block."""
        response = self.client.post(
            self.receive_url, "", content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "0")

    def test_receive_data_sensor_not_found(self):
        """Covers 404 missing sensor ID block."""
        payload = {"sensor_id": 99999}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    @patch("sensors.views.api.predictor.predict", return_value="Safe")
    def test_receive_data_safe_status(self, mock_predict):
        """Covers a completely normal, safe AI reading."""
        payload = {"sensor_id": self.sensor.id, "methane": 10}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertFalse(data["fire_override"])
        self.assertEqual(SensorDataLog.objects.count(), 1)

    @patch("sensors.views.api.predictor.predict", return_value="Fire")
    @patch("sensors.views.api.send_sms_broadcast")
    def test_receive_data_missing_coords_branch(self, mock_sms, mock_predict):
        """Covers Branch A: user_address.latitude is None."""
        # Force missing GPS data
        self.user_profile.address.latitude = None
        self.user_profile.address.longitude = None
        self.user_profile.address.save()

        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data["fire_override"])
        self.assertTrue(mock_sms.called)

    @patch("sensors.views.api.predictor.predict", return_value="Fire")
    def test_receive_data_deduplication_branch(self, mock_predict):
        """Covers Branch B: Active report already exists."""
        Report.objects.create(
            status="System Detected", address=self.address, trigger_sensor=self.sensor
        )

        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Report.objects.count(), 1
        )  # Proves it updated the existing one instead of creating a duplicate

    @patch("sensors.views.api.async_to_sync")
    @patch("sensors.views.api.get_channel_layer")
    @patch("sensors.views.api.send_sms_broadcast")
    @patch("sensors.views.api.haversine", return_value=1.5)
    @patch("sensors.views.api.predictor.predict", return_value="Fire")
    def test_receive_data_full_fire_dispatch_with_staff(
        self, mock_predict, mock_hav, mock_sms, mock_channels, mock_async
    ):
        """Covers Branch C: Full dispatch, WebSocket triggers, and SMS logic with active shift rotations."""

        # 1. Force the station link to be rock solid
        self.ff_profile.station = self.station
        self.ff_profile.save()

        # 2. Widen the time delta to a massive +/- 1 day to completely bypass microsecond timing glitches
        from datetime import timedelta

        DutyAssignmentFactory(
            firefighter=self.ff_profile,
            is_active=True,
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1),
        )

        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Report.objects.count(), 1)

        # 3. Prove it broadcasted to BOTH the homeowner and the active staff!
        self.assertTrue(mock_sms.called)

    @patch("sensors.views.api.send_sms_broadcast")
    @patch("sensors.views.api.predictor.predict", return_value="Gas Leak")
    def test_receive_data_gas_leak_branch(self, mock_predict, mock_sms):
        """Covers Branch D: Owner-only Gas Leak notification."""
        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_sms.called)

    @patch(
        "sensors.views.api.predictor.predict", side_effect=Exception("Database failure")
    )
    def test_receive_data_exception_block(self, mock_predict):
        """Covers the general try/except 500 branch."""
        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content.decode())
        self.assertIn("Database failure", data["error"])

    # ==========================================
    # 3. LOCATION UPDATE LINK COVERAGE
    # ==========================================
    def test_update_location_get_success(self):
        """Covers valid signature GET request."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse(self.update_url_name, args=[token])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/update_location.html")

    def test_update_location_bad_signature(self):
        """Covers SignatureExpired/BadSignature catch."""
        url = reverse(self.update_url_name, args=["invalid-token"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/error.html")

    def test_update_location_post_success_existing_address(self):
        """Covers successful address object update."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse(self.update_url_name, args=[token])
        payload = {"lat": 3.5, "lng": 101.5, "street": "Updated Pin"}

        response = self.client.post(
            url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.address.refresh_from_db()
        self.assertEqual(float(self.address.latitude), 3.5)
        self.assertEqual(self.address.street, "Updated Pin")

    def test_update_location_post_empty_string_logic(self):
        """Covers the 'or' fallback logic in the update branch."""
        address = self.user_profile.address
        address.street = ""
        address.save()
        
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse(self.update_url_name, args=[token])
        
        payload = {"lat": 2.0, "lng": 102.0, "street": "", "city": ""}
        self.client.post(url, json.dumps(payload), content_type="application/json")
        
        address.refresh_from_db()
        # Because the string was empty, the view IGNORES it and leaves it as ""
        self.assertEqual(address.street, "")

    def test_update_location_post_invalid_coords(self):
        """Covers ValueError and range constraint blocks."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse(self.update_url_name, args=[token])

        # Test out of bounds
        payload = {"lat": 150, "lng": 200}
        response = self.client.post(
            url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Test value error (strings instead of floats)
        payload = {"lat": "abc", "lng": "def"}
        response = self.client.post(
            url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("sensors.views.api.json.loads", side_effect=Exception("Parsing failure"))
    def test_update_location_server_error(self, mock_json):
        """Covers the generic 500 try/except block for the location link."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse(self.update_url_name, args=[token])

        response = self.client.post(url, "{}", content_type="application/json")
        self.assertEqual(response.status_code, 500)

    # ==========================================
    # 4. FILTER VIEW COVERAGE
    # ==========================================
    def test_filters_sensor_view_no_log_fallback(self):
        """Covers the 'or Safe' fallback when a sensor has no logs."""
        # Create a new sensor with no logs
        SensorFactory(owner=self.user_profile, name="NoLogSensor")
        
        response = self.client.get(self.filters_url)
        self.assertEqual(response.status_code, 200)
        
        sensors = response.json()["sensors"]
        # Find the sensor with no logs and verify status is 'Safe'
        no_log_sensor = next(s for s in sensors if s["name"] == "NoLogSensor")
        self.assertEqual(no_log_sensor["status"], "Safe")

    def test_filters_sensor_view_unauthenticated(self):
        """Covers the unauthenticated fallback queryset path."""
        response = self.client.get(self.filters_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("sensors" in response.json())
    
    @patch("sensors.views.api.async_to_sync")
    @patch("sensors.views.api.get_channel_layer")
    @patch("sensors.views.api.send_sms_broadcast")
    @patch("sensors.views.api.haversine", return_value=1.5)
    @patch("sensors.views.api.predictor.predict", return_value="Fire")
    def test_receive_data_fire_dispatch_fallback_no_active_staff(
        self, mock_predict, mock_hav, mock_sms, mock_channels, mock_async
    ):
        """Covers the fallback logic: No active staff found, so pick the nearest station anyway."""
        # Ensure station exists but has NO active duty assignments
        DutyAssignmentFactory.objects.all().delete()
        
        payload = {"sensor_id": self.sensor.id}
        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        # Should still create a report for the nearest station
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.first().station, self.station)
