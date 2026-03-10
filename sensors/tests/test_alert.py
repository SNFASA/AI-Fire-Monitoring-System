from django.test import TestCase, Client
from django.urls import reverse
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
        except:
            self.url = reverse('receive_data')

        # 1. FIXED COORDINATES: Ensures the view's 'if latitude/longitude' logic passes
        self.owner_addr = AddressFactory(latitude=3.1390, longitude=101.6869)
        self.station_addr = AddressFactory(latitude=3.1400, longitude=101.6900)

        # 2. OWNER SETUP
        self.owner_profile = UserProfileFactory(
            role='public', 
            address=self.owner_addr,
            phone_number='+60123456789'
        )

        # 3. STATION & FIREFIGHTER SETUP
        self.station = FireStationFactory(address=self.station_addr)
        self.ff_profile = UserProfileFactory(
            role='firefighter', 
            station=self.station,
            phone_number='+60198765432'
        )

        # 4. SENSOR SETUP
        self.sensor = SensorFactory(owner=self.owner_profile)

        # 5. DUTY ASSIGNMENT: Explicitly created for staff search logic
        DutyAssignment.objects.create(
            firefighter=self.ff_profile,
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
        mock_hav.return_value = 1.2
        mock_async.side_effect = lambda func: lambda *args, **kwargs: None

        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800, "lpg": 700, "co": 300, 
            "dht22_temp": 65.5, "humidity": 20, "flame_val": 100 
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Report.objects.count(), 1, "Report should be created when Fire is detected")
        self.assertTrue(mock_sms.called, "Alerts should have been sent")

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
        
        # Create an existing report
        Report.objects.create(status='System Detected', address=self.owner_addr, station=self.station, trigger_sensor=self.sensor)
        
        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")
        
        # Count should remain 1 (updated, not new)
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