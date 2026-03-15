from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from unittest.mock import patch
from sensors.models import Sensor, SensorDataLog, UserProfile
from sensors.utils import get_sensor_status, get_live_logs
from sensors.views.api import test_log
from django.contrib.auth.models import User


class GetSensorStatusTestCase(TestCase):
    """Tests for get_sensor_status helper function"""

    def setUp(self):
        # 1. Create User (Signal automatically creates UserProfile here)
        self.user = User.objects.create_user(username="testuser", password="pass123")

        # 2. FIX: Fetch the auto-created profile instead of creating a new one
        self.profile = self.user.userprofile
        self.profile.role = "public"
        self.profile.save()

        # 3. Create Sensor
        self.sensor = Sensor.objects.create(owner=self.profile, name="Test Sensor")

    def create_dummy_log(self, status, timestamp, methane=300.0):
        """Creates a SensorDataLog with default fake values to prevent database crashes"""
        return SensorDataLog.objects.create(
            sensor=self.sensor,
            status=status,
            timestamp=timestamp,
            methane=methane,
            lpg=300.0,
            co=80.0,
            air_quality=90.0,
            flame_val=4095.0,
            dht22_temp=28.0,
            humidity=60.0,
        )

    # --- Test Cases ---

    def test_offline_no_logs(self):
        """Sensor with no logs should return Offline"""
        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "Offline")

    def test_offline_stale_data(self):
        """Sensor with data older than 5 minutes should return Offline"""
        old_time = timezone.now() - timedelta(minutes=6)
        # Use update() to force a specific timestamp (auto_now_add usually blocks manual setting)
        log = self.create_dummy_log(status="Safe", timestamp=old_time)
        SensorDataLog.objects.filter(id=log.id).update(timestamp=old_time)

        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "Offline")

    def test_returns_fire_status(self):
        """Sensor with Fire status should return Fire"""
        recent_time = timezone.now() - timedelta(minutes=2)
        self.create_dummy_log(status="Fire", timestamp=recent_time, methane=800.0)
        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "Fire")

    def test_returns_safe_status(self):
        """Sensor with Safe status should return Safe"""
        recent_time = timezone.now() - timedelta(minutes=2)
        self.create_dummy_log(status="Safe", timestamp=recent_time)
        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "Safe")

    def test_normalizes_gasleak_status(self):
        """GasLeak status should be normalized to 'gas leak'"""
        recent_time = timezone.now() - timedelta(minutes=2)
        self.create_dummy_log(status="GasLeak", timestamp=recent_time, methane=500.0)
        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "gas leak")

    def test_returns_warning_status(self):
        """Sensor with Warning status should return Warning"""
        recent_time = timezone.now() - timedelta(minutes=2)
        self.create_dummy_log(status="Warning", timestamp=recent_time, methane=500.0)
        status = get_sensor_status(self.sensor)
        self.assertEqual(status, "Warning")


class GetLiveLogsTestCase(TestCase):
    """Tests for get_live_logs view"""

    def setUp(self):
        self.factory = RequestFactory()

    @patch("sensors.utils.get_logs")
    def test_get_live_logs_returns_json(self, mock_get_logs):
        """get_live_logs should return JsonResponse with logs"""
        mock_get_logs.return_value = ["log1", "log2"]
        request = self.factory.get("/logs/")
        response = get_live_logs(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"logs", response.content)

    @patch("sensors.utils.get_logs")
    def test_get_live_logs_empty_logs(self, mock_get_logs):
        """get_live_logs should handle empty logs"""
        mock_get_logs.return_value = []
        request = self.factory.get("/logs/")
        response = get_live_logs(request)

        self.assertEqual(response.status_code, 200)


class TestLogTestCase(TestCase):
    """Tests for test_log view"""

    def setUp(self):
        self.factory = RequestFactory()

    @patch("sensors.views.api.add_log")
    def test_log_adds_entry(self, mock_add_log):
        """test_log should call add_log with test message"""
        request = self.factory.get("/test-log/")
        response = test_log(request)

        mock_add_log.assert_called_once_with("\n[TEST] This is a test log entry.\n")
        self.assertEqual(response.status_code, 200)

    @patch("sensors.views.api.add_log")
    def test_log_returns_json_response(self, mock_add_log):
        """test_log should return json with status"""
        request = self.factory.get("/test-log/")
        response = test_log(request)

        self.assertIn(b"Log added", response.content)
