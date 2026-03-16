import json
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch
from .factories import (
    UserProfileFactory,
    SensorFactory,
    AddressFactory,
    FireStationFactory,
    HouselayoutFactory,
)
from ..models import Houselayout, Address


class MapAndLayoutCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Firefighter (Safely bypassing Django Signals)
        self.station_addr = AddressFactory(latitude=3.12, longitude=101.5)
        self.station = FireStationFactory(
            address=self.station_addr, cover_area_sqm=3141592
        )  # ~1km radius

        temp_ff = UserProfileFactory()
        self.ff = temp_ff.user.userprofile
        self.ff.role = "firefighter"
        self.ff.station = self.station
        self.ff.save()

        # 2. Setup Public User with Layout (Safely bypassing Django Signals)
        self.public_addr = AddressFactory(latitude=3.13, longitude=101.6)

        temp_public = UserProfileFactory()
        self.public_user = temp_public.user.userprofile
        self.public_user.role = "public"
        self.public_user.address = self.public_addr
        self.public_user.save()

        self.layout = HouselayoutFactory(user=self.public_user.user, name="Floor 1")
        self.sensor = SensorFactory(owner=self.public_user, layout=self.layout)

    # --- firefighter_map_data Tests ---

    def test_map_data_auth_and_filtering(self):
        """Covers role check and coordinate filtering logic."""
        # Unauth check
        self.client.login(
            username=self.public_user.user.username, password="password123"
        )
        response = self.client.get(reverse("sensors:map_data"))
        self.assertEqual(response.status_code, 403)

        # Success path + Coordinate check
        self.client.login(username=self.ff.user.username, password="password123")
        # Add a user with NULL coords to test the 'if profile.address' skip
        temp_null = UserProfileFactory()
        null_user = temp_null.user.userprofile
        null_user.address = AddressFactory(latitude=None)
        null_user.save()

        response = self.client.get(reverse("sensors:map_data"))
        data = response.json()
        self.assertEqual(len(data["houses"]), 1)  # Only the valid public_user

    @patch("sensors.views.maps.get_sensor_status")
    def test_map_status_prioritization(self, mock_status):
        """Covers the status loop (Fire > Gas Leak > Offline)."""
        mock_status.return_value = "Fire"
        self.client.login(username=self.ff.user.username, password="password123")

        response = self.client.get(reverse("sensors:map_data"))
        self.assertEqual(response.json()["houses"][0]["status"], "Fire")

    # --- maps View Tests ---

    def test_maps_public_layout_selection(self):
        """Covers public role layout selection logic."""
        self.client.login(
            username=self.public_user.user.username, password="password123"
        )

        # Test with layout_id param
        url = f"{reverse('sensors:maps')}?layout_id={self.layout.id}"
        response = self.client.get(url)
        self.assertEqual(response.context["current_layout"].id, self.layout.id)

    def test_maps_firefighter_gps_guard(self):
        """Covers the 'has_gps' logic and radius calculation."""
        self.client.login(username=self.ff.user.username, password="password123")

        # Success path
        response = self.client.get(reverse("sensors:maps"))
        self.assertAlmostEqual(response.context["station_radius"], 1.0, places=4)
        self.assertFalse(response.context["missing_station_gps"])

        # Missing GPS path
        self.station_addr.latitude = None
        self.station_addr.save()
        response = self.client.get(reverse("sensors:maps"))
        self.assertTrue(response.context["missing_station_gps"])

    # --- AJAX Layout Management ---

    def test_get_victim_layout_success(self):
        """Covers firefighter fetching public user's layout."""
        self.client.login(username=self.ff.user.username, password="password123")
        url = reverse("sensors:get_victim_layout", args=[self.public_user.user.id])
        response = self.client.get(url)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(len(response.json()["layouts"]), 1)

    def test_edit_layout_ajax_success_and_errors(self):
        """Covers edit_layout file upload and ObjectDoesNotExist branches."""
        self.client.login(
            username=self.public_user.user.username, password="password123"
        )
        url = reverse("sensors:edit_layout_ajax")

        # 1. Success with Image
        new_img = SimpleUploadedFile("new.png", b"data", content_type="image/png")
        data = {"layout_id": self.layout.id, "name": "Renamed", "image": new_img}
        response = self.client.post(url, data)
        self.assertEqual(response.json()["success"], True)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.name, "Renamed")

        # 2. Not Found branch
        response = self.client.post(url, {"layout_id": 999})
        self.assertEqual(response.status_code, 404)

    # --- Station Coordinates ---

    def test_update_station_coordinates_branches(self):
        """Covers JSONDecodeError and missing coordinate branches."""
        self.client.login(username=self.ff.user.username, password="password123")
        # FIX: Changed URL name to match urls.py exactly
        url = reverse("sensors:update_station_coords")

        # 1. Missing coords
        response = self.client.post(
            url, json.dumps({"lat": None}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # 2. JSON Error
        response = self.client.post(url, "not-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # 3. Success
        response = self.client.post(
            url, json.dumps({"lat": 4.0, "lng": 102.0}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
