from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .factories import (
    UserProfileFactory,
    SensorFactory,
    MaintenanceFactory,
    MaintenanceImageFactory,
    FireStationFactory,
)
from ..models import Maintenance, MaintenanceImage


class MaintenanceCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Users (Safely bypassing the Django Signal Trap!)
        temp_ff = UserProfileFactory()
        self.ff = temp_ff.user.userprofile
        self.ff.role = "firefighter"
        self.ff.save()

        temp_owner = UserProfileFactory()
        self.owner = temp_owner.user.userprofile
        self.owner.role = "public"
        self.owner.save()

        temp_hacker = UserProfileFactory()
        self.hacker = temp_hacker.user.userprofile
        self.hacker.role = "public"
        self.hacker.save()

        # 2. Setup Sensor and Maintenance
        self.sensor = SensorFactory(owner=self.owner)
        self.task = MaintenanceFactory(sensor=self.sensor, status="Pending")

        self.detail_url = reverse("sensors:maintenance_detail", args=[self.task.id])
        self.edit_url = reverse("sensors:maintenance_edit", args=[self.task.id])

    def test_maintenance_access_denied(self):
        """Covers the PermissionDenied branch in _check_maintenance_access."""
        self.client.login(username=self.hacker.user.username, password="password123")
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 403)  # Permission Denied

    def test_maintenance_view_role_filtering(self):
        # 1. Use your factory! This automatically creates the Address, cover area, etc. behind the scenes!
        station = FireStationFactory()

        # 2. Make sure your test firefighter profile is assigned to this exact generated station
        self.ff.role = "firefighter"
        self.ff.station = station
        self.ff.save()

        # 3. Create a Maintenance record assigned to the EXACT SAME station
        Maintenance.objects.create(
            sensor=self.sensor,  # Assuming you created a test sensor
            maintenance_type="HealthCheck",
            nearest_fire_station=station,  # THIS IS THE CRITICAL LINK
            details="Test details",
        )

        # 4. Now perform your login and test the view
        self.client.force_login(self.ff.user)
        response = self.client.get(reverse("sensors:maintenance"))

        # This should now pass with flying colors!
        self.assertGreaterEqual(len(response.context["maintenance_items"]), 1)

    def test_upload_evidence(self):
        """Covers upload_maintenance_evidence branch."""
        self.client.login(username=self.owner.user.username, password="password123")
        pic = SimpleUploadedFile("test.jpg", b"file_content", content_type="image/jpeg")

        url = reverse("sensors:upload_maintenance_evidence", args=[self.task.id])
        response = self.client.post(url, {"picture": pic})

        self.assertRedirects(response, self.detail_url)
        self.assertEqual(MaintenanceImage.objects.count(), 1)

    def test_edit_maintenance_firefighter_path(self):
        """Covers the 'Firefighter/Technician Logic' branch in edit_maintenance."""
        self.client.login(username=self.ff.user.username, password="password123")
        data = {
            "status": "Completed",
            "technician_notes": "All sensors calibrated.",
            "actual_date": "2026-03-20",
        }
        response = self.client.post(self.edit_url, data)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "Completed")
        self.assertEqual(self.task.in_charge, self.ff.user)

    def test_handle_images_delete_branch(self):
        """Covers the delete_images logic in handle_images helper."""
        self.client.login(username=self.owner.user.username, password="password123")
        img = MaintenanceImageFactory(maintenance=self.task)

        # Give the form ALL the required fields it needs to naturally pass validation
        data = {
            "sensor": self.sensor.id,
            "maintenance_type": self.task.maintenance_type,
            "scheduled_date": self.task.scheduled_date.strftime("%Y-%m-%d"),
            "details": "Checking the sensor.",
            "status": "Pending",
            "delete_images": [img.id],  # The actual target of our test
        }

        # Remove the @patch wrapper and just post the valid data
        response = self.client.post(self.edit_url, data)

        # Ensure the image was actually deleted from the database
        self.assertEqual(MaintenanceImage.objects.filter(id=img.id).count(), 0)

    def test_delete_maintenance_success(self):
        """Covers delete_maintenance success path."""
        self.client.login(username=self.ff.user.username, password="password123")
        url = reverse("sensors:delete_maintenance", args=[self.task.id])
        response = self.client.post(url)

        self.assertRedirects(response, reverse("sensors:maintenance"))
        self.assertFalse(Maintenance.objects.filter(id=self.task.id).exists())
