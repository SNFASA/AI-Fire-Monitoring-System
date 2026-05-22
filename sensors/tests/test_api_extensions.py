import json
import uuid  # <-- ADD THIS IMPORT
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from sensors.models import Sensor, SensorDataLog, Report, UserProfile, Address

class ComprehensiveApiTests(TestCase):

    def setUp(self):
        # FIX 1: Generate a globally unique username to guarantee pristine record states
        unique_suffix = uuid.uuid4().hex[:6]
        username_str = f"owner_{unique_suffix}"
        
        # FIX 2: Create the user entry 
        self.user = User.objects.create_user(username=username_str, password="pass")
        
        # Clear any cached backward relationship profiles before building
        if hasattr(self.user, 'userprofile'):
            self.user.userprofile.delete()

        # Safely create the profile
        self.profile = UserProfile.objects.create(
            user=self.user, 
            role="public", 
            phone_number="+601139771785"
        )
        
        self.address = Address.objects.create(
            street="Jalan UTHM", 
            city="Batu Pahat", 
            state="Johor", 
            latitude=1.8532, 
            longitude=103.0864
        )
        self.profile.address = self.address
        self.profile.save()

        self.sensor = Sensor.objects.create(id=80, name="Simulated Unit", owner=self.profile)
        self.url = "/api/send-data/"
        
    def test_http_method_not_allowed(self):
        """Covers if request.method != 'POST' path block."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_empty_request_body(self):
        """Covers if not request.body path block."""
        response = self.client.post(self.url, "", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "0")

    @patch("sensors.views.api.predictor.predict")
    def test_alert_deduplication_branch(self, mock_predict):
        """Covers the active_report update branch path when duplicate fire events hit."""
        mock_predict.return_value = "Fire"
        
        # Seed an existing report inside the system database layout
        existing_report = Report.objects.create(status="System Detected", address=self.address, trigger_sensor=self.sensor)
        initial_update_time = existing_report.updated

        payload = {"sensor_id": 80, "flame_val": 300, "dht22_temp": 50.0}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        # Ensure a new duplicate report was not spun up
        self.assertEqual(Report.objects.count(), 1)