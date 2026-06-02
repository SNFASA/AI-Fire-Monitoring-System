import json

from django.test import Client, TestCase
from django.urls import reverse

from ..models import Sensor, UserProfile
from .factories import (
    FireStationFactory,
    MaintenanceFactory,
    ReportFactory,
    SensorDataLogFactory,
    SensorFactory,
    UserProfileFactory,
)


class DashboardCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Setup Staff User
        self.staff_user = UserProfileFactory(role="firefighter").user
        self.staff_user.userprofile.role = "firefighter"
        self.staff_user.userprofile.save()
        # Setup Public User
        self.public_user = UserProfileFactory(role="public").user

        # Setup Sensors
        self.public_sensor = SensorFactory(
            owner=self.public_user.userprofile, name="Public Sensor"
        )
        self.other_sensor = SensorFactory(name="Other Sensor")

    def test_dashboard_view_creates_profile_if_missing(self):
        """Covers the UserProfile.DoesNotExist branch."""
        # Create a user without a factory (so no profile is created by signals)
        from django.contrib.auth.models import User

        new_user = User.objects.create_user(username="noprofile", password="pass")
        self.client.login(username="noprofile", password="pass")

        response = self.client.get(reverse("sensors:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=new_user).exists())

    def test_dashboard_view_role_filtering(self):
        """Covers the if/else logic for sensor visibility based on role."""
        # Test Public Role
        self.client.login(username=self.public_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard"))
        self.assertEqual(response.context["sensors_count"], 1)

        # Test Staff Role
        self.client.login(username=self.staff_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard"))
        self.assertGreaterEqual(response.context["sensors_count"], 2)

    def test_get_dashboard_sensor_data_subquery(self):
        """Covers the Subquery and Prefetch logic for latest readings."""
        # Create multiple logs for one sensor
        SensorDataLogFactory(
            sensor=self.public_sensor, dht22_temp=20.0, timestamp="2026-01-01 10:00:00"
        )
        latest_log = SensorDataLogFactory(
            sensor=self.public_sensor,
            dht22_temp=35.5,
            status="Fire",
            timestamp="2026-01-01 12:00:00",
        )

        self.client.login(username=self.public_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard_data"))

        data = response.json()
        self.assertEqual(data["sensors"][0]["temp"], "35.5")
        self.assertEqual(data["sensors"][0]["status"], "Fire")

    def test_delete_sensor_standard_success_and_fail(self):
        """Covers delete_sensor successful delete and DoesNotExist branches."""
        self.client.login(username=self.public_user.username, password="password123")

        # 1. Success path
        url = reverse("sensors:delete_sensor", args=[self.public_sensor.id])
        response = self.client.post(url)
        self.assertRedirects(response, reverse("sensors:dashboard"))
        self.assertFalse(Sensor.objects.filter(id=self.public_sensor.id).exists())

        # 2. Permission Denied / Not Found path
        url = reverse("sensors:delete_sensor", args=[self.other_sensor.id])
        response = self.client.post(url)
        # Should redirect but show error message
        self.assertEqual(response.status_code, 302)

    def test_delete_sensor_ajax_success_and_fail(self):
        """Covers delete_sensor_ajax success and 404 branches."""
        self.client.login(username=self.public_user.username, password="password123")

        # 1. Success path
        url = reverse("sensors:delete_sensor_ajax", args=[self.public_sensor.id])
        response = self.client.post(url)
        self.assertEqual(response.json()["success"], True)

        # 2. 404 path (Permission denied or ID wrong)
        url = reverse("sensors:delete_sensor_ajax", args=[self.other_sensor.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)
    
    def test_get_dashboard_sensor_data_offline_fallback(self):
        """Covers the branch where a sensor has no logs ('Offline')."""
        # Create a sensor with no logs
        empty_sensor = SensorFactory(owner=self.public_user.userprofile, name="Empty")
        
        self.client.login(username=self.public_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard_data"))
        
        # Check that the Empty sensor returns 'Offline' status
        data = response.json()
        empty_data = next(s for s in data["sensors"] if s["name"] == "Empty")
        self.assertEqual(empty_data["status"], "Offline")
        self.assertEqual(empty_data["temp"], "N/A")

    def test_get_dashboard_sensor_data_null_values(self):
        """Covers the case where log exists but values are None."""
        SensorDataLogFactory(sensor=self.public_sensor, dht22_temp=0.0, humidity=0.0)
        
        self.client.login(username=self.public_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard_data"))
        
        data = response.json()
        sensor_data = next(s for s in data["sensors"] if s["id"] == self.public_sensor.id)
        self.assertEqual(sensor_data["temp"], "N/A")
        self.assertEqual(sensor_data["hum"], "N/A")
    
    def test_dashboard_view_full_context(self):
        """Covers Maintenance and Report context queries."""
        MaintenanceFactory(status="Pending")
        ReportFactory()
        
        self.client.login(username=self.staff_user.username, password="password123")
        response = self.client.get(reverse("sensors:dashboard"))
        
        self.assertEqual(response.context["maintenance_pending"], 1)
        self.assertGreaterEqual(response.context["reports_count"], 1)
    
    def test_delete_sensor_ajax_non_existent_id(self):
        """Covers the strict DoesNotExist path."""
        self.client.login(username=self.public_user.username, password="password123")
        
        url = reverse("sensors:delete_sensor_ajax", args=[99999])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)