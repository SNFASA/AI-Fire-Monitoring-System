import json
from unittest.mock import patch

from django.core.signing import TimestampSigner
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Address, Report, User, UserProfile
from .factories import (
    AddressFactory,
    FireStationFactory,
    SensorFactory,
    UserProfileFactory,
)


class AlertSystemCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.signer = TimestampSigner()

        # 1. Safely setup the profile and address bypassing signal bugs
        self.user_profile = UserProfileFactory(role="public")
        self.address = AddressFactory(latitude=None, longitude=None)

        # Manually force the connection to ensure it is never None
        self.user_profile.address = self.address
        self.user_profile.phone_number = "0123456789"
        self.user_profile.save()

        self.sensor = SensorFactory(owner=self.user_profile)
        self.station_addr = AddressFactory(latitude=3.1, longitude=101.1)
        self.station = FireStationFactory(address=self.station_addr)

        self.receive_url = reverse("sensors:receive_data")

    # --- receive_sensor_data Tests ---
    def test_receive_data_exception_handling(self):
        """Covers the 'except Exception as e' branch."""
        # Sending non-JSON data to trigger a JSONDecodeError/Exception
        response = self.client.post(
            self.receive_url, "invalid-data", content_type="application/json"
        )

    @patch("sensors.views.api.predictor.predict")
    @patch("sensors.views.api.send_sms_broadcast")
    def test_receive_data_missing_coords_branch(self, mock_sms, mock_predict):
        """Covers the if user_address.latitude is None branch."""
        mock_predict.return_value = "Fire"
        payload = {"sensor_id": self.sensor.id, "methane": 500}

        response = self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "1")
        self.assertTrue(mock_sms.called)

    @patch("sensors.views.api.predictor.predict")
    @patch("sensors.views.api.haversine")  # FIX: Path updated to api.haversine
    @patch("sensors.views.api.async_to_sync")
    def test_receive_data_fire_success_and_deduplication(
        self, mock_async, mock_hav, mock_predict
    ):
        """Covers successful report creation AND deduplication (active_report) branches."""
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 1.0
        # Mocking the WebSocket async wrapper
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        # Set coordinates so we bypass the missing GPS check
        self.address.latitude, self.address.longitude = 3.0, 101.0
        self.address.save()

        payload = {"sensor_id": self.sensor.id, "temp": 45}

        # First Run: Create Report
        self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(Report.objects.count(), 1)

        # Second Run: Deduplication (active_report branch)
        self.client.post(
            self.receive_url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(Report.objects.count(), 1)  # Still 1

    def test_receive_data_invalid_method(self):
        """Covers the status=405 branch."""
        response = self.client.get(self.receive_url)
        self.assertEqual(response.status_code, 405)

    def test_receive_data_exception_handling(self):
        """Covers the 'except Exception as e' branch."""
        # Sending non-JSON data to trigger a JSONDecodeError/Exception
        response = self.client.post(
            self.receive_url, "invalid-data", content_type="application/json"
        )
        self.assertEqual(response.content.decode(), "0")

    # --- update_location_from_link Tests ---

    def test_update_location_get_success(self):
        """Covers valid signature GET request."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse("sensors:update_location_link", args=[token])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/update_location.html")

    def test_update_location_bad_signature(self):
        """Covers SignatureExpired/BadSignature branch."""
        url = reverse("sensors:update_location_link", args=["invalid-token"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)  # Django renders error page
        self.assertTemplateUsed(response, "sensors/error.html")

    def test_update_location_post_success(self):
        """Covers valid POST coordinate update."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse("sensors:update_location_link", args=[token])
        payload = {"lat": 3.123, "lng": 101.456}

        response = self.client.post(
            url, json.dumps(payload), content_type="application/json"
        )

        # FIX: Refresh the direct address instance instead of through the relationship
        self.address.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(self.address.latitude), 3.123)

    def test_update_location_post_invalid_coords(self):
        """Covers invalid coordinate/data validation branch."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse("sensors:update_location_link", args=[token])

        # Test out of range coordinates
        payload = {"lat": 100, "lng": 200}
        response = self.client.post(
            url, json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_update_location_server_error(self):
        """Covers the 'except Exception' branch in update_location."""
        token = self.signer.sign(str(self.user_profile.id))
        url = reverse("sensors:update_location_link", args=[token])

        # Send empty body to trigger exception
        response = self.client.post(url, "", content_type="application/json")
        self.assertEqual(response.status_code, 500)


class LocationUpdateTests(TestCase):
    def setUp(self):
        # 1. Use the standard Client
        self.client = Client()

        # 2. Create the User first
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

        # 3. FIX: Safely get the auto-created profile (or create if missing)
        self.profile, created = UserProfile.objects.get_or_create(user=self.user)

        # Ensure it has no address for our test scenario
        self.profile.address = None
        self.profile.save()

        self.signer = TimestampSigner()
        self.signed_id = self.signer.sign(self.profile.id)

        # 4. Use the namespaced URL name
        self.url = reverse("sensors:update_location_link", args=[self.signed_id])

    def test_create_address_when_none_exists(self):
        """
        Verify that if a profile has no address, the view creates one
        and links it correctly.
        """
        payload = {
            "lat": 34.0522,
            "lng": -118.2437,
            "street": "123 Main St",
            "city": "Los Angeles",
            "state": "CA",
            "postal_code": "90012",
        }

        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        # Refresh profile from DB
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.address)
        self.assertEqual(float(self.profile.address.latitude), 34.0522)
        self.assertEqual(self.profile.address.street, "123 Main St")

    def test_create_address_with_empty_fields_uses_fallbacks(self):
        """
        Verify that fallbacks work when geocoding data is missing.
        """
        payload = {"lat": 0.0, "lng": 0.0, "street": "", "city": ""}

        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.address.street, "Emergency Location (GPS Pin)")
        self.assertEqual(self.profile.address.city, "Unknown")
