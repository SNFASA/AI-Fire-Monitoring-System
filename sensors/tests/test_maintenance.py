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
        self.public_profile = UserProfileFactory(role='public')
        self.public_user = self.public_profile.user 

        # 2. Firefighter User
        self.firefighter_profile = UserProfileFactory(role='firefighter')
        self.firefighter = self.firefighter_profile.user

        # 3. Create Sensor 
        self.sensor = SensorFactory(owner=self.public_profile)

        # 4. Create Maintenance Request
        self.maintenance = MaintenanceFactory(
            sensor=self.sensor,
            status='Pending', 
            details='Initial details'
        )

        # 5. Dummy Image
        self.image_file = SimpleUploadedFile(
            name='test_image.jpg', 
            content=b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04\x00', 
            content_type='image/jpeg'
        )

    def test_create_maintenance_success(self):
        self.client.force_login(self.public_user)
        url = reverse('maintenance_create')
        
        data = {
            'sensor': self.sensor.id,
            'maintenance_type': 'HealthCheck', 
            'frequency': 'monthly',
            'details': 'New Request',
            'scheduled_date': date.today(),
            'images': [self.image_file],
            'status': 'Pending' 
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('maintenance'))
        self.assertEqual(Maintenance.objects.count(), 2)

    def test_public_can_edit_pending(self):
        self.client.force_login(self.public_user)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        data = {
            'sensor': self.sensor.id,
            'maintenance_type': 'HealthCheck', 
            'frequency': 'monthly',
            'details': 'Updated by Factory Boy',
            'scheduled_date': date.today(),
            'status': 'Pending' 
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.maintenance.refresh_from_db()
        self.assertEqual(self.maintenance.details, 'Updated by Factory Boy')

    def test_public_cannot_edit_processing(self):
        self.maintenance.status = 'In Progress' 
        self.maintenance.save()
        
        self.client.force_login(self.public_user)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        self.client.post(url, {'details': 'Hacked'})
        
        self.maintenance.refresh_from_db()
        self.assertNotEqual(self.maintenance.details, 'Hacked')

    def test_firefighter_update(self):
        self.client.force_login(self.firefighter)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        # We must send ALL fields required by the view manual update
        data = {
            'status': 'Completed', 
            'actual_date': date.today().isoformat(), # Send as string
            'technician_notes': 'Fixed via Test',
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.maintenance.refresh_from_db()
        
        # Debugging: If this fails, the view treated user as 'public'
        if self.maintenance.status != 'Completed':
            print(f"\n[DEBUG] Status failed to update. Current role: {self.firefighter.userprofile.role}")

        self.assertEqual(self.maintenance.status, 'Completed')
        self.assertEqual(self.maintenance.in_charge, self.firefighter)

    def test_delete_maintenance(self):
        self.client.force_login(self.public_user)
        url = reverse('delete_maintenance', args=[self.maintenance.id])
        
        response = self.client.post(url, follow=True)
        self.assertEqual(Maintenance.objects.count(), 0)