from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from sensors.models import (
    Sensor, SensorDataLog, FireStation, Address, 
    Report, UserProfile, DutyAssignment
)
import json
from unittest.mock import patch

class AlertSystemTest(TestCase):

    def setUp(self):
        """
        Setup run before every test method.
        """
        self.client = Client()
        # Fallback URL finding
        try:
            self.url = reverse('sensors:receive_data')
        except:
            self.url = reverse('receive_data')

        # 1. Create Owner User
        self.owner_user = User.objects.create_user(username='owner', password='password')
        
        # Create Address for Owner
        self.owner_address = Address.objects.create(
            street="123 Owner St", city="Shah Alam", state="Selangor",
            latitude=3.0738, longitude=101.5183
        )

        # Create Profile (handling auto-creation signals if they exist)
        self.owner_profile, created = UserProfile.objects.get_or_create(user=self.owner_user)
        self.owner_profile.role = 'public'
        self.owner_profile.phone_number = "+60123456789"
        self.owner_profile.address = self.owner_address
        self.owner_profile.save()

        # 2. Create Fire Station
        self.station_address = Address.objects.create(
            street="999 Fire Lane", city="Shah Alam", state="Selangor",
            latitude=3.0740, longitude=101.5190
        )

        self.station = FireStation.objects.create(
            name="Shah Alam Station",
            address=self.station_address,
            cover_area_sqm=5000, 
            contact_number="999",
            email="station@bomba.gov.my"
        )

        # 3. Create Firefighter
        self.ff_user = User.objects.create_user(username='firefighter', password='password')
        self.ff_profile, created = UserProfile.objects.get_or_create(user=self.ff_user)
        self.ff_profile.role = 'firefighter'
        self.ff_profile.phone_number = "+60198765432"
        self.ff_profile.station = self.station
        self.ff_profile.rank = 'PB'
        self.ff_profile.save()

        # Assign Duty
        DutyAssignment.objects.create(
            firefighter=self.ff_profile,
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=8),
            is_active=True
        )

        # 4. Create Sensor
        self.sensor = Sensor.objects.create(
            name="Kitchen Sensor",
            owner=self.owner_profile,
            is_active=True
        )

    # --- UPDATED TEST METHOD ---
    @patch('sensors.views.async_to_sync')          
    @patch('sensors.views.predictor.predict')      
    @patch('sensors.views.send_sms_broadcast')     
    @patch('sensors.views.get_channel_layer')      
    def test_fire_detected_scenario(self, mock_channel, mock_sms, mock_predict, mock_async_to_sync):
        """
        Scenario: AI predicts 'Fire'.
        Expectation: Report created, SMS sent, Response '1'.
        """
        # Configure mocks
        mock_predict.return_value = "Fire"
        # Make async_to_sync return a dummy function that does nothing
        mock_async_to_sync.side_effect = lambda *args, **kwargs: lambda *a, **k: None

        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800, "lpg": 700, "co": 300, 
            "dht22_temp": 65.5, "humidity": 20,
            "flame_val": 100 
        }

        # Run POST request
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "1") 

        # Check DB for Report
        self.assertEqual(Report.objects.count(), 1)
        report = Report.objects.first()
        self.assertEqual(report.status, 'System Detected')
        self.assertEqual(report.station, self.station)
        
        # Check SMS calls
        self.assertTrue(mock_sms.called)
        self.assertEqual(mock_sms.call_count, 2)

    @patch('sensors.views.predictor.predict')
    def test_safe_scenario(self, mock_predict):
        """
        Scenario: AI predicts 'Safe'.
        Expectation: Log created, NO Report created, Response '0'.
        """
        mock_predict.return_value = "Safe"

        payload = {
            "sensor_id": self.sensor.id,
            "methane": 50, "dht22_temp": 28, "humidity": 60
        }

        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "0") 

        self.assertEqual(SensorDataLog.objects.count(), 1)
        self.assertEqual(Report.objects.count(), 0)

    @patch('sensors.views.predictor.predict')
    def test_deduplication_logic(self, mock_predict):
        """
        Scenario: Fire detected, but a Report already exists.
        Expectation: Update existing report timestamp, DO NOT create new report.
        """
        mock_predict.return_value = "Fire"

        # Pre-create an active report
        existing_report = Report.objects.create(
            status='System Detected',
            address=self.owner_address,
            station=self.station,
            trigger_sensor=self.sensor
        )

        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Assert: Still only 1 report
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.first().id, existing_report.id)

    @patch('sensors.views.predictor.predict')
    def test_no_active_staff_fallback(self, mock_predict):
        """
        Scenario: Fire detected, but no firefighters are on duty.
        Expectation: Create report anyway, assigned to nearest station (fallback).
        """
        mock_predict.return_value = "Fire"

        DutyAssignment.objects.all().delete()

        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        

        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.first().station, self.station)

    def test_invalid_sensor_id(self):
        """
        Scenario: Sensor ID does not exist in DB.
        Expectation: Graceful failure (return 0), no crash.
        """
        payload = {"sensor_id": 999999}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "0")

    def test_invalid_method_get(self):
        """
        Scenario: GET request instead of POST.
        Expectation: 405 Method Not Allowed.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)