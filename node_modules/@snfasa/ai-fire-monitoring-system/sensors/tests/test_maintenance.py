from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from datetime import date
from sensors.models import Maintenance
from .factories import UserProfileFactory, MaintenanceFactory, SensorFactory


class MaintenanceViewTests(TestCase):

    def setUp(self):
        self.client = Client()

        # 1. Public User
        self.public_profile = UserProfileFactory(role="public")
        self.public_user = self.public_profile.user

        # 2. Firefighter User
        # Force the role assignment explicitly to be safe
        self.firefighter_profile = UserProfileFactory(role="firefighter")
        self.firefighter_profile.role = "firefighter"
        self.firefighter_profile.save()
        self.firefighter = self.firefighter_profile.user

        # 3. Create Sensor
        self.sensor = SensorFactory(owner=self.public_profile)

        # 4. Create Maintenance Request
        self.maintenance = MaintenanceFactory(
            sensor=self.sensor, status="Pending", details="Initial details"
        )

        self.image_file = SimpleUploadedFile(
            name="test_image.jpg",
            content=b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04\x00",
            content_type="image/jpeg",
        )

    def test_create_maintenance_success(self):
        self.client.force_login(self.public_user)
        url = reverse("sensors:maintenance_create")

        data = {
            "sensor": self.sensor.id,
            "maintenance_type": "HealthCheck",
            "frequency": "monthly",
            "details": "New Request",
            "scheduled_date": date.today(),
            "images": [self.image_file],
            "status": "Pending",
        }

        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse("sensors:maintenance"))
        self.assertEqual(Maintenance.objects.count(), 2)

    def test_public_can_edit_pending(self):
        self.client.force_login(self.public_user)
        url = reverse("sensors:maintenance_edit", args=[self.maintenance.id])

        data = {
            "sensor": self.sensor.id,
            "maintenance_type": "HealthCheck",
            "frequency": "monthly",
            "details": "Updated by Factory Boy",
            "scheduled_date": date.today(),
            "status": "Pending",
        }

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.maintenance.refresh_from_db()
        self.assertEqual(self.maintenance.details, "Updated by Factory Boy")

    def test_public_cannot_edit_processing(self):
        self.maintenance.status = "In Progress"
        self.maintenance.save()

        self.client.force_login(self.public_user)
        url = reverse("sensors:maintenance_edit", args=[self.maintenance.id])

        self.client.post(url, {"details": "Hacked"})

        self.maintenance.refresh_from_db()
        self.assertNotEqual(self.maintenance.details, "Hacked")

    def test_firefighter_update(self):
        self.client.force_login(self.firefighter)
        url = reverse("sensors:maintenance_edit", args=[self.maintenance.id])

        data = {
            "status": "Completed",
            "actual_date": date.today().isoformat(),  # Send as string (YYYY-MM-DD)
            "technician_notes": "Fixed via Test",
        }

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.maintenance.refresh_from_db()
        self.assertEqual(self.maintenance.status, "Completed")
        self.assertEqual(self.maintenance.in_charge, self.firefighter)

    def test_delete_maintenance(self):
        self.client.force_login(self.public_user)
        url = reverse("sensors:delete_maintenance", args=[self.maintenance.id])

        response = self.client.post(url, follow=True)
        self.assertEqual(Maintenance.objects.count(), 0)
