# sensors/tests/test_filters.py
import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from sensors.filters import MaintenanceFilter, ReportFilter, SensorFilter
from sensors.models import Address, Maintenance, Report, Sensor, UserProfile


class FilterSystemTests(TestCase):

    def setUp(self):
        # 1. Setup global users and profiles cleanly using unique string sets
        unique_suffix = uuid.uuid4().hex[:6]
        username_str = f"bomba_tester_{unique_suffix}"

        self.user = User.objects.create_user(
            username=username_str, password="password123"
        )

        if hasattr(self.user, "userprofile"):
            self.user.userprofile.delete()

        self.profile = UserProfile.objects.create(user=self.user, role="firefighter")

        self.address = Address.objects.create(
            street="Jalan Universiti",
            city="Parit Raja",
            state="Johor",
            postal_code="86400",
        )
        self.profile.address = self.address
        self.profile.save()

        # 2. Seed Mock Data for Sensor Tests
        self.sensor_kitchen = Sensor.objects.create(
            id=101, name="Kitchen MQ-5 Sensor", is_active=True, owner=self.profile
        )
        self.sensor_bedroom = Sensor.objects.create(
            id=102, name="Bedroom DHT22 Sensor", is_active=False, owner=self.profile
        )

        # 3. Seed Mock Data for Maintenance Tests
        self.maint_1 = Maintenance.objects.create(
            sensor=self.sensor_kitchen,
            status="Completed",
            maintenance_type="Calibration",
            frequency="Monthly",
            scheduled_date=timezone.now().date(),
        )
        self.maint_2 = Maintenance.objects.create(
            sensor=self.sensor_bedroom,
            status="Pending",
            maintenance_type="Replacement",
            frequency="Annual",
            scheduled_date=timezone.now().date(),
        )

        # 4. Seed Mock Data for Report Incident Tests
        self.report_fire = Report.objects.create(
            id=501,
            status="System Detected",
            is_approved=False,
            trigger_sensor=self.sensor_kitchen,
            address=self.address,
        )
        self.report_false = Report.objects.create(
            id=502,
            status="False Alarm",
            is_approved=True,
            trigger_sensor=self.sensor_bedroom,
            address=self.address,
        )

    def test_sensor_custom_search_by_id(self):
        """Ensure search parameter filters down to accurate numerical primary keys."""
        qs = Sensor.objects.all()
        f = SensorFilter(data={"q": "101"}, queryset=qs)
        self.assertIn(self.sensor_kitchen, f.qs)
        self.assertNotIn(self.sensor_bedroom, f.qs)

    def test_sensor_custom_search_by_name(self):
        """Ensure search matches case-insensitive substring combinations."""
        qs = Sensor.objects.all()
        f = SensorFilter(data={"q": "Kitchen"}, queryset=qs)
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.sensor_kitchen, f.qs)

    def test_sensor_realtime_status_passthrough(self):
        """Verify passing 'All' string resets filter scope context."""
        qs = Sensor.objects.all()
        for sensor in qs:
            sensor.current_status = "Safe"

        f = SensorFilter(data={"status": "All"}, queryset=qs)
        self.assertEqual(f.qs.count(), 2)

    def test_maintenance_status_case_insensitive(self):
        """Verify case-insensitive matching filters statuses correctly."""
        qs = Maintenance.objects.all()
        f = MaintenanceFilter(data={"status": "completed"}, queryset=qs)
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.maint_1, f.qs)

    def test_maintenance_custom_search_by_sensor_name(self):
        """Ensure parsing digit logic spans downstream related foreign key names."""
        qs = Maintenance.objects.all()
        f = MaintenanceFilter(data={"search": "Bedroom"}, queryset=qs)
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.maint_2, f.qs)

    def test_report_built_in_boolean_filter(self):
        """Verify the built-in BooleanFilter checks boolean conditions smoothly."""
        qs = Report.objects.all()

        f_approved = ReportFilter(data={"is_approved": "true"}, queryset=qs)
        self.assertIn(self.report_false, f_approved.qs)
        self.assertNotIn(self.report_fire, f_approved.qs)

    def test_report_status_all_option(self):
        """Verify passing case-insensitive fallback 'all' fetches complete sets."""
        qs = Report.objects.all()
        f = ReportFilter(data={"status": "all"}, queryset=qs)
        self.assertEqual(f.qs.count(), 2)

    def test_report_custom_search_by_id_or_sensor(self):
        """Ensure search parses numerical primary IDs or linked sensor trigger strings."""
        qs = Report.objects.all()
        f = ReportFilter(data={"search": "501"}, queryset=qs)
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.report_fire, f.qs)
