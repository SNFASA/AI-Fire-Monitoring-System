import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import patch, PropertyMock
from ..models import Address, Houselayout
from .factories import (
    AddressFactory,
    FireStationFactory,
    HouselayoutFactory,
    SensorFactory,
    UserProfileFactory,
)


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

    @patch("sensors.views.maps.get_sensor_status")
    def test_map_status_gas_leak_priority(self, mock_status):
        """Covers the gas leak logic in the map loop."""
        # Setup: Return gas leak
        mock_status.return_value = "gas leak"
        self.client.login(username=self.ff.user.username, password="password123")

        response = self.client.get(reverse("sensors:map_data"))
        self.assertEqual(response.json()["houses"][0]["status"], "gas leak")
    
    def test_wildfire_map_unauthorized(self):
        """Covers the unauthorized view branch."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.get(reverse("sensors:wildfire_map"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/layout/unauthorized.html")
    
    def test_update_station_coords_no_address(self):
        """Mock the address property since the DB strictly forbids null addresses."""
        self.client.login(username=self.ff.user.username, password="password123")
        url = reverse("sensors:update_station_coords")
        
        # We mock the address property of the FireStation model to temporarily return None
        with patch("sensors.models.FireStation.address", new_callable=PropertyMock) as mock_address:
            mock_address.return_value = None
            response = self.client.post(url, json.dumps({"lat": 1, "lng": 1}), content_type="application/json")
            
        self.assertEqual(response.status_code, 404)
    
    def test_wildfire_api_branches(self):
        """Covers various error branches in wildfire_api_view."""
        self.client.login(username=self.public_user.user.username, password="password123")
        
        # 1. Unauthorized
        response = self.client.post(reverse("sensors:wildfire_api"))
        self.assertEqual(response.status_code, 403)
        
        # 2. No station assigned
        self.ff.station = None
        self.ff.save()
        self.client.login(username=self.ff.user.username, password="password123")
        response = self.client.post(reverse("sensors:wildfire_api"))
        self.assertEqual(response.status_code, 400)
    
    def test_delete_layout_ajax_exception(self):
        """Triggers the generic Exception block."""
        self.client.login(username=self.public_user.user.username, password="password123")
        
        # Manually corrupt the object to trigger Exception during delete
        with patch.object(Houselayout, 'delete', side_effect=Exception("DB Failure")):
            response = self.client.post(reverse("sensors:delete_layout_ajax", args=[self.layout.id]))
            self.assertRedirects(response, reverse("sensors:maps"))
    
    # ==========================================
    # 1. MAP DATA & MAPS VIEW
    # ==========================================

    @patch("sensors.views.maps.get_sensor_status", return_value="Offline")
    def test_map_status_offline_priority(self, mock_status):
        """Covers the branch where all sensors are safe but one is offline."""
        self.client.login(username=self.ff.user.username, password="password123")
        response = self.client.get(reverse("sensors:map_data"))
        self.assertEqual(response.json()["houses"][0]["status"], "Offline")

    def test_maps_view_no_profile(self):
        """Covers the UserProfile.DoesNotExist branch in maps view."""
        from django.contrib.auth.models import User
        ghost = User.objects.create_user("ghost3", password="password123")
        self.client.login(username="ghost3", password="password123")
        
        response = self.client.get(reverse("sensors:maps"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["role"], "unknown")

    def test_maps_public_default_layout(self):
        """Covers the 'else user_layouts.first()' logic in maps view."""
        self.client.login(username=self.public_user.user.username, password="password123")
        # Do not pass a layout_id
        response = self.client.get(reverse("sensors:maps"))
        self.assertEqual(response.context["current_layout"].id, self.layout.id)


    # ==========================================
    # 2. UPLOAD LAYOUT (Completely Missing)
    # ==========================================

    def test_upload_layout_get(self):
        """Covers the GET branch of upload_layout."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.get(reverse("sensors:upload_layout"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/upload_layout.html")

    def test_upload_layout_post_success(self):
        """Covers successful POST branch in upload_layout."""
        self.client.login(username=self.public_user.user.username, password="password123")
        img = SimpleUploadedFile("layout.jpg", b"data", content_type="image/jpeg")
        
        response = self.client.post(reverse("sensors:upload_layout"), {"name": "Floor 2", "image": img})
        self.assertRedirects(response, reverse("sensors:maps"))

    def test_upload_layout_post_invalid(self):
        """Covers invalid form branch in upload_layout."""
        self.client.login(username=self.public_user.user.username, password="password123")
        # Missing image will cause form to be invalid
        response = self.client.post(reverse("sensors:upload_layout"), {"name": "Floor 3"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)


    # ==========================================
    # 3. AJAX LAYOUT MANAGEMENT
    # ==========================================

    def test_get_victim_layout_unauthorized(self):
        """Covers public user trying to fetch victim layout."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.get(reverse("sensors:get_victim_layout", args=[self.public_user.user.id]))
        self.assertEqual(response.status_code, 403)

    def test_delete_layout_ajax_success(self):
        """Covers the successful deletion path."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.post(reverse("sensors:delete_layout_ajax", args=[self.layout.id]))
        self.assertRedirects(response, reverse("sensors:maps"))
        self.assertEqual(Houselayout.objects.count(), 0)

    def test_edit_layout_ajax_missing_id(self):
        """Covers 'if not layout_id' branch."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.post(reverse("sensors:edit_layout_ajax"), {})
        self.assertEqual(response.status_code, 400)

    def test_edit_layout_ajax_invalid_id(self):
        """Covers ValueError/TypeError branch."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.post(reverse("sensors:edit_layout_ajax"), {"layout_id": "invalid_string"})
        self.assertEqual(response.status_code, 400)


    # ==========================================
    # 4. STATION COORDINATES
    # ==========================================

    def test_update_station_coords_unauthorized(self):
        """Covers the 403 Unauthorized branch (Public User)."""
        self.client.login(username=self.public_user.user.username, password="password123")
        response = self.client.post(reverse("sensors:update_station_coords"), json.dumps({"lat": 1, "lng": 1}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    @patch("sensors.models.Address.save", side_effect=Exception("DB Error"))
    def test_update_station_coords_exception(self, mock_save):
        """Covers the generic 500 exception block."""
        self.client.login(username=self.ff.user.username, password="password123")
        response = self.client.post(reverse("sensors:update_station_coords"), json.dumps({"lat": 1, "lng": 1}), content_type="application/json")
        self.assertEqual(response.status_code, 500)


    # ==========================================
    # 5. WILDFIRE MAPS & API
    # ==========================================

    def test_wildfire_map_view_success(self):
        """Covers the successful rendering path of wildfire maps."""
        self.client.login(username=self.ff.user.username, password="password123")
        response = self.client.get(reverse("sensors:wildfire_map"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["missing_station_gps"])

    def test_wildfire_api_no_address(self):
        """Covers station.address is None."""
        self.client.login(username=self.ff.user.username, password="password123")
        with patch("sensors.models.FireStation.address", new_callable=PropertyMock) as mock_address:
            mock_address.return_value = None
            response = self.client.post(reverse("sensors:wildfire_api"))
            self.assertEqual(response.status_code, 404)

    def test_wildfire_api_missing_coords(self):
        """Covers lat/lng is None."""
        self.station_addr.latitude = None
        self.station_addr.save()
        self.client.login(username=self.ff.user.username, password="password123")
        response = self.client.post(reverse("sensors:wildfire_api"))
        self.assertEqual(response.status_code, 404)

    def test_wildfire_api_success_and_json_error(self):
        """Covers the JSONDecodeError fallback and the actual success loop."""
        self.client.login(username=self.ff.user.username, password="password123")
        
        # 1. Create a dummy hotspot for the loop
        from sensors.models import SatelliteHotspot
        from django.contrib.gis.geos import Point
        from django.utils import timezone
        SatelliteHotspot.objects.create(
            location=Point(101.0, 3.0),
            brightness=300,
            acq_date=timezone.now().date(),
            acq_time="1200",
            satellite="TEST",
            confidence="h",
            frp=10.0
        )

        # 2. Valid JSON payload
        response = self.client.post(reverse("sensors:wildfire_api"), json.dumps({"days": 2}), content_type="application/json")
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(len(response.json()["active_hotspots"]), 1)

        # 3. Invalid JSON (Triggers `except (ValueError, json.JSONDecodeError)`)
        response = self.client.post(reverse("sensors:wildfire_api"), "invalid_json_string", content_type="application/json")
        self.assertEqual(response.json()["success"], True)