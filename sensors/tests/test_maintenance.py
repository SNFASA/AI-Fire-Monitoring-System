from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from datetime import date

# 1. Import Models
from sensors.models import Maintenance, MaintenanceImage

# 2. Import Factories (Fixed Import Path)
from .factories import UserProfileFactory, MaintenanceFactory, SensorFactory

class MaintenanceViewTests(TestCase):

    def setUp(self):
        self.client = Client()

        # 1. Public User
        self.public_profile = UserProfileFactory(role='public')
        self.public_user = self.public_profile.user 

        # 2. Firefighter User
        self.firefighter_profile = UserProfileFactory(role='firefighter')
        # Force save role to ensure it sticks
        self.firefighter_profile.role = 'firefighter'
        self.firefighter_profile.save()
        self.firefighter = self.firefighter_profile.user

        # 3. Create Sensor 
        self.sensor = SensorFactory(owner=self.public_profile)

        # 4. Create Maintenance Request
        # FIX: Use 'Pending' (Capital P) to match your Model Choices exactly
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

    # =========================================================
    # TEST 1: CREATE MAINTENANCE
    # =========================================================
    def test_create_maintenance_success(self):
        self.client.force_login(self.public_user)
        url = reverse('maintenance_create')
        
        data = {
            'sensor': self.sensor.id,
            'maintenance_type': 'HealthCheck', 
            'frequency': 'monthly',         # Required field
            'details': 'New Request',
            'scheduled_date': date.today(),
            'images': [self.image_file],
            # Status is usually excluded from Create forms, so we might not need it here
            'status': 'Pending' 
        }
        
        response = self.client.post(url, data, follow=True)
        
        self.assertRedirects(response, reverse('maintenance'))
        self.assertEqual(Maintenance.objects.count(), 2)

    # =========================================================
    # TEST 2: PUBLIC EDIT (The One Failing)
    # =========================================================
    def test_public_can_edit_pending(self):
        self.client.force_login(self.public_user)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        data = {
            'sensor': self.sensor.id,
            'maintenance_type': 'HealthCheck', 
            'frequency': 'monthly',         # Required field
            'details': 'Updated by Factory Boy',
            'scheduled_date': date.today(),
            # FIX: We must send status because {{ form.as_p }} likely renders it
            'status': 'Pending' 
        }
        
        response = self.client.post(url, data)
        
        # --- DEBUG PRINT ---
        # This will print to your console if the form is still invalid
        if response.context and 'form' in response.context:
            if response.context['form'].errors:
                print("\n⚠️ FORM ERRORS FOUND:", response.context['form'].errors)
        # -------------------

        self.maintenance.refresh_from_db()
        self.assertEqual(self.maintenance.details, 'Updated by Factory Boy')

    # =========================================================
    # TEST 3: PUBLIC EDIT (Blocked if Processing)
    # =========================================================
    def test_public_cannot_edit_processing(self):
        # Change status to In Progress (Capitalized)
        self.maintenance.status = 'In Progress' 
        self.maintenance.save()
        
        self.client.force_login(self.public_user)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        self.client.post(url, {'details': 'Hacked'})
        
        self.maintenance.refresh_from_db()
        self.assertNotEqual(self.maintenance.details, 'Hacked')

    # =========================================================
    # TEST 4: FIREFIGHTER UPDATE
    # =========================================================
    def test_firefighter_update(self):
        self.client.force_login(self.firefighter)
        url = reverse('maintenance_edit', args=[self.maintenance.id])
        
        data = {
            # FIX: Use 'Completed' (Capital C) to match Model Choices
            'status': 'Completed', 
            'actual_date': date.today(),
            'technician_notes': 'Fixed via Test',
        }
        
        self.client.post(url, data)
        self.maintenance.refresh_from_db()
        
        self.assertEqual(self.maintenance.status, 'Completed')
        self.assertEqual(self.maintenance.in_charge, self.firefighter)

    # =========================================================
    # TEST 5: DELETE MAINTENANCE
    # =========================================================
    def test_delete_maintenance(self):
        self.client.force_login(self.public_user)
        url = reverse('delete_maintenance', args=[self.maintenance.id])
        
        response = self.client.post(url, follow=True)
        self.assertEqual(Maintenance.objects.count(), 0)