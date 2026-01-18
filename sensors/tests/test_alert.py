from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from sensors.models import SensorDataLog, Report, DutyAssignment, FireStation
from .factories import UserProfileFactory, SensorFactory, FireStationFactory, AddressFactory
import json
from unittest.mock import patch

class AlertSystemTest(TestCase):

    def setUp(self):
        self.client = Client()
        try:
            self.url = reverse('sensors:receive_data')
        except:
            self.url = reverse('receive_data')

        # 1. Create Public User (Owner) WITH PHONE NUMBER
        self.owner_profile = UserProfileFactory(role='public', phone_number='+60123456789')
        if not self.owner_profile.address:
            self.owner_profile.address = AddressFactory()
            self.owner_profile.save()

        # 2. Create Fire Station & Firefighter WITH PHONE NUMBER
        self.station = FireStationFactory()
        self.ff_profile = UserProfileFactory(role='firefighter', phone_number='+60198765432')
        self.ff_profile.station = self.station
        self.ff_profile.save()

        # 3. Create Sensor
        self.sensor = SensorFactory(owner=self.owner_profile, name="Kitchen Sensor")

        # 4. Assign Duty (Ensure times cover NOW)
        DutyAssignment.objects.create(
            firefighter=self.ff_profile,
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=8),
            is_active=True
        )

    @patch('sensors.views.async_to_sync')          
    @patch('sensors.views.predictor.predict')      
    @patch('sensors.views.send_sms_broadcast')     
    @patch('sensors.views.get_channel_layer')      
    def test_fire_detected_scenario(self, mock_channel, mock_sms, mock_predict, mock_async_to_sync):
        mock_predict.return_value = "Fire"
        # Mock async_to_sync to simply execute the function passed to it
        mock_async_to_sync.side_effect = lambda func: lambda *args, **kwargs: None

        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800, "lpg": 700, "co": 300, 
            "dht22_temp": 65.5, "humidity": 20,
            "flame_val": 100 
        }

        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "1") 
        
        # Check that SMS was tried at least once (for Owner OR Firefighter)
        self.assertTrue(mock_sms.called, "SMS should be sent to Owner or Firefighter")

    @patch('sensors.views.predictor.predict')
    def test_safe_scenario(self, mock_predict):
        mock_predict.return_value = "Safe"
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 50, "dht22_temp": 28, "humidity": 60
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.content.decode(), "0") 
        self.assertEqual(SensorDataLog.objects.count(), 1)
        self.assertEqual(Report.objects.count(), 0)

    @patch('sensors.views.predictor.predict')
    def test_deduplication_logic(self, mock_predict):
        mock_predict.return_value = "Fire"
        Report.objects.create(
            status='System Detected',
            address=self.owner_profile.address,
            station=self.station,
            trigger_sensor=self.sensor
        )
        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(Report.objects.count(), 1)

    @patch('sensors.views.predictor.predict')
    def test_no_active_staff_fallback(self, mock_predict):
        mock_predict.return_value = "Fire"
        DutyAssignment.objects.all().delete() # No staff on duty

        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(Report.objects.count(), 1)
        # Should fallback to the nearest station
        self.assertEqual(Report.objects.first().station, self.station)

    def test_invalid_sensor_id(self):
        payload = {"sensor_id": 999999}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.content.decode(), "0")

    def test_invalid_method_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)