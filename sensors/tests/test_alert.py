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

        # 1. Create Public User (Owner)
        # We explicitly set lat/long to ensure they are not None
        self.owner_addr = AddressFactory(latitude=1.0, longitude=1.0)
        self.owner_profile = UserProfileFactory(
            role='public', 
            phone_number='+60123456789', 
            address=self.owner_addr
        )

        # 2. Create Fire Station
        self.station_addr = AddressFactory(latitude=1.02, longitude=1.0) # Nearby
        self.station = FireStationFactory(address=self.station_addr)
        
        self.ff_profile = UserProfileFactory(role='firefighter', phone_number='+60198765432')
        self.ff_profile.station = self.station
        self.ff_profile.save()

        # 3. Create Sensor linked to Owner
        self.sensor = SensorFactory(owner=self.owner_profile, name="Kitchen Sensor")

        # 4. Assign Duty
        # We make the window very large to avoid timezone mismatches
        DutyAssignment.objects.create(
            firefighter=self.ff_profile,
            start_time=timezone.now() - timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1),
            is_active=True
        )

    # -------------------------------------------------------------------------
    # TEST 1: FIRE SCENARIO (MOCK EVERYTHING)
    # -------------------------------------------------------------------------
    @patch('sensors.views.async_to_sync')          
    @patch('sensors.views.predictor.predict')      
    @patch('sensors.views.send_sms_broadcast')     
    @patch('sensors.views.get_channel_layer') 
    @patch('sensors.views.haversine')  # <--- CRITICAL FIX: Mock Distance Calc
    def test_fire_detected_scenario(self, mock_hav, mock_channel, mock_sms, mock_predict, mock_async_to_sync):
        # 1. Setup Mocks
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 1.5 # Fake distance: 1.5 km
        mock_async_to_sync.side_effect = lambda func: lambda *args, **kwargs: None

        # 2. Send Data
        payload = {
            "sensor_id": self.sensor.id,
            "methane": 800, "lpg": 700, "co": 300, 
            "dht22_temp": 65.5, "humidity": 20,
            "flame_val": 100 
        }
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # 3. Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "1") 
        
        # Verify Report was created
        self.assertEqual(Report.objects.count(), 1, "Report should be created when Fire is detected")
        
        # Verify SMS was sent (This confirms Station + Staff were found)
        self.assertTrue(mock_sms.called, "SMS should be sent to Owner or Firefighter")

    # -------------------------------------------------------------------------
    # TEST 2: SAFE SCENARIO
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # TEST 3: DEDUPLICATION
    # -------------------------------------------------------------------------
    @patch('sensors.views.predictor.predict')
    def test_deduplication_logic(self, mock_predict):
        mock_predict.return_value = "Fire"
        
        # Create an existing report
        Report.objects.create(
            status='System Detected',
            address=self.owner_addr,
            station=self.station,
            trigger_sensor=self.sensor
        )
        
        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")
        
        # Should still be 1 report (updated, not duplicated)
        self.assertEqual(Report.objects.count(), 1)

    # -------------------------------------------------------------------------
    # TEST 4: FALLBACK (NO STAFF)
    # -------------------------------------------------------------------------
    @patch('sensors.views.haversine') # <--- CRITICAL FIX
    @patch('sensors.views.predictor.predict')
    def test_no_active_staff_fallback(self, mock_predict, mock_hav):
        mock_predict.return_value = "Fire"
        mock_hav.return_value = 5.0 # Fake distance: 5 km
        
        # Delete all staff duties
        DutyAssignment.objects.all().delete() 

        payload = {"sensor_id": self.sensor.id, "dht22_temp": 90}
        self.client.post(self.url, json.dumps(payload), content_type="application/json")

        # Should still create report assigned to nearest station (even if no staff)
        self.assertEqual(Report.objects.count(), 1, "Report should be created even if no staff are on duty")
        self.assertEqual(Report.objects.first().station, self.station)

    # -------------------------------------------------------------------------
    # TEST 5: ERROR HANDLING
    # -------------------------------------------------------------------------
    def test_invalid_sensor_id(self):
        payload = {"sensor_id": 999999}
        response = self.client.post(self.url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.content.decode(), "0")

    def test_invalid_method_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)