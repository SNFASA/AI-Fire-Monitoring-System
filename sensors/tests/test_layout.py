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
        # We assume the signal creates the profile, but we fetch/create to be safe
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user, defaults={'role': 'public'})
        
        # Login
        self.client.login(username='testuser', password='password123')

        # 2. URLs (ensure these names match your urls.py exactly)
        self.upload_url = reverse('upload_layout')
        self.add_sensor_url = reverse('add_sensor')
        self.update_pos_url = reverse('update_sensor_pos')

    def test_upload_layout_success(self):
        """TC-001: Test uploading a valid image for the layout"""
        # Create a tiny dummy image file in memory (GIF header)
        image_content = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        uploaded_file = SimpleUploadedFile("layout.gif", image_content, content_type="image/gif")
        
        data = {
            'name': 'My Dream House',
            'image': uploaded_file
        }
        
        response = self.client.post(self.upload_url, data)
        
        # Should redirect to maps page on success
        self.assertRedirects(response, reverse('maps'))
        
        # Verify DB
        layout = Houselayout.objects.filter(user=self.user).first()
        self.assertIsNotNone(layout)
        self.assertEqual(layout.name, 'My Dream House')
        # Cleanup: Delete the file created
        layout.image.delete()

    def test_add_sensor_api(self):
        """TC-002: Test adding a sensor via JSON API"""
        # Ideally create a layout first so the sensor can link to it (if your model requires it)
        layout = Houselayout.objects.create(user=self.user, name="Test Layout", image="test.jpg")

        data = {'name': 'Living Room Sensor'}
        
        response = self.client.post(
            self.add_sensor_url, 
            data=json.dumps(data), 
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['name'], 'Living Room Sensor')
        
        # Verify DB
        sensor = Sensor.objects.filter(owner=self.profile, name='Living Room Sensor').first()
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor.x_position, 5.0) # Default value check
        self.assertEqual(sensor.layout, layout)

    def test_update_sensor_position(self):
        """TC-003: Test updating X/Y coordinates of a sensor"""
        # Create a sensor first
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
        # Create profile for hacker manually if signal doesn't exist/work in test env
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