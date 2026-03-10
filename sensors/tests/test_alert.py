from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from sensors.models import SensorDataLog, Report, DutyAssignment, FireStation, Sensor
import json
from unittest.mock import patch
from .factories import UserProfileFactory, SensorFactory, FireStationFactory, AddressFactory

class AlertSystemTest(TestCase):
    def setUp(self):
        self.client = Client()
        try:
            self.url = reverse('sensors:receive_data')
        except NoReverseMatch:
            self.url = reverse('sensors:receive_data')

        # Setup address and owner correctly
        self.addr = AddressFactory(latitude=3.1390, longitude=101.6869)
        self.owner = UserProfileFactory(role='public', address=self.addr)
        
        self.sensor = Sensor.objects.create(
            owner=self.owner,
            name="Test Sensor",
            latitude=3.1390,
            longitude=101.6869,
            is_active=True
        )
        
        self.station = FireStationFactory(address=AddressFactory(latitude=3.1400, longitude=101.6900))
        self.ff = UserProfileFactory(role='firefighter', station=self.station)
        
        DutyAssignment.objects.create(
            firefighter=self.ff,
            start_time=timezone.now() - timezone.timedelta(hours=1),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            is_active=True
        )

    @patch('sensors.views.async_to_sync')          
    @patch('sensors.views.predictor.predict')      
    @patch('sensors.views.send_sms_broadcast')     
    @patch('sensors.views.get_channel_layer') 
    @patch('sensors.views.haversine')
    def test_fire_detected_scenario(self, mock_hav, mock_channel, mock_sms, mock_predict, mock_async):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 0.5
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800, "lpg": 700, "co": 300, 
            "dht22_temp": 65.5, "humidity": 20, "flame_val": 100 
        }
        
        # We clear reports before the test to be 100% sure
        Report.objects.all().delete()
        
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Debug print in case it fails again in CI
        if Report.objects.count() == 0:
            print(f"DEBUG: Response Content: {response.content.decode()}")

        self.assertEqual(Report.objects.count(), 1)

    @patch('sensors.views.predictor.predict')
    def test_safe_scenario(self, mock_predict):
        mock_predict.return_value = "Safe"
        payload = {"sensor_id": self.sensor.id, "methane": 50, "dht22_temp": 28}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        
        self.assertEqual(response.content.decode(), "0") 
        self.assertEqual(Report.objects.count(), 0)

    @patch('sensors.views.haversine')
    @patch('sensors.views.predictor.predict')
    def test_deduplication_logic(self, mock_predict, mock_hav):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 1.0
        
        # FIX: Changed self.owner_addr to self.addr
        Report.objects.create(
            status='System Detected', 
            address=self.addr, 
            station=self.station, 
            trigger_sensor=self.sensor
        )
        
        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(Report.objects.count(), 1)

    @patch('sensors.views.haversine') 
    @patch('sensors.views.predictor.predict')
    @patch('sensors.views.async_to_sync')
    def test_no_active_staff_fallback(self, mock_async, mock_predict, mock_hav):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 5.0
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None
        
        # Clear all duties
        DutyAssignment.objects.all().delete() 

        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Should fall back to nearest station even if no staff
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.first().station, self.station)

    def test_invalid_sensor_id(self):
        payload = {"sensor_id": 999999}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.content.decode(), "0")

    def test_invalid_method_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)