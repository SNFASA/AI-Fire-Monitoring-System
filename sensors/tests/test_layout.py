import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from sensors.models import UserProfile, Sensor, Houselayout

class LayoutAndSensorTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Create a Test User and Profile
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user, defaults={'role': 'public'})
        
        # Login
        self.client.login(username='testuser', password='password123')

        # 2. URLs
        self.upload_url = reverse('upload_layout')
        self.add_sensor_url = reverse('add_sensor')
        self.update_pos_url = reverse('update_sensor_pos')

    def test_upload_layout_success(self):
        """TC-001: Test uploading multiple layouts"""
        # Create a tiny dummy image file in memory
        image_content = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        
        # Upload Layout 1
        file1 = SimpleUploadedFile("layout1.gif", image_content, content_type="image/gif")
        self.client.post(self.upload_url, {'name': 'Ground Floor', 'image': file1})

        # Upload Layout 2
        file2 = SimpleUploadedFile("layout2.gif", image_content, content_type="image/gif")
        self.client.post(self.upload_url, {'name': 'Second Floor', 'image': file2})
        
        # Verify DB has 2 layouts for this user
        layouts = Houselayout.objects.filter(user=self.user)
        self.assertEqual(layouts.count(), 2)
        self.assertEqual(layouts[0].name, 'Ground Floor')
        self.assertEqual(layouts[1].name, 'Second Floor')

    def test_add_sensor_api(self):
        """TC-002: Test adding a sensor linked to a specific layout"""
        # 1. Create a layout manually first
        layout = Houselayout.objects.create(user=self.user, name="Test Layout", image="test.jpg")

        # 2. Send payload WITH layout_id
        data = {
            'name': 'Living Room Sensor',
            'layout_id': layout.id  # <--- CRITICAL UPDATE
        }
        
        response = self.client.post(
            self.add_sensor_url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        # 3. Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        
        # Verify DB
        sensor = Sensor.objects.filter(owner=self.profile, name='Living Room Sensor').first()
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor.layout, layout) # Ensure it is linked to the correct floor

    def test_update_sensor_position(self):
        """TC-003: Test updating X/Y coordinates of a sensor"""
        # Create sensor
        sensor = Sensor.objects.create(
            owner=self.profile, 
            name="Moveable Sensor",
            x_position=10, 
            y_position=10
        )
        
        new_pos = {
            'sensor_id': sensor.id,
            'x': 55.5,
            'y': 80.2
        }
        
        response = self.client.post(
            self.update_pos_url,
            data=json.dumps(new_pos),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        # Refresh from DB
        sensor.refresh_from_db()
        self.assertEqual(sensor.x_position, 55.5)
        self.assertEqual(sensor.y_position, 80.2)

    def test_cannot_update_others_sensor(self):
        """TC-004: Security Check - Ensure user cannot move another user's sensor"""
        # Create another user (The Hacker)
        other_user = User.objects.create_user(username='hacker', password='password123')
        UserProfile.objects.get_or_create(user=other_user, defaults={'role': 'public'})
        
        # Create a sensor owned by the FIRST user (Original user from setUp)
        victim_sensor = Sensor.objects.create(
            owner=self.profile, 
            name="Victim Sensor",
            x_position=10, 
            y_position=10
        )
        
        # Login as the Hacker
        self.client.logout()
        self.client.login(username='hacker', password='password123')
        
        payload = {
            'sensor_id': victim_sensor.id,
            'x': 0,
            'y': 0
        }
        
        response = self.client.post(
            self.update_pos_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        # Expect failure (success: False)
        self.assertFalse(response.json()['success'])
        
        # Verify position did NOT change in DB
        victim_sensor.refresh_from_db()
        self.assertEqual(victim_sensor.x_position, 10)