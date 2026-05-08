from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .factories import (
    UserProfileFactory,
    ReportFactory,
    FireStationFactory,
    DutyAssignmentFactory,
)
from ..models import Report


class MobilizationCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Stations
        self.station_a = FireStationFactory(name="Station Alpha")
        self.station_b = FireStationFactory(name="Station Beta")

        # 2. Setup Firefighters (Safely bypassing signals)
        # Fetch the exact signal-created profile from the DB and update it
        temp_a = UserProfileFactory()
        self.ff_a = temp_a.user.userprofile
        self.ff_a.role = "firefighter"
        self.ff_a.station = self.station_a
        self.ff_a.save()

        temp_b = UserProfileFactory()
        self.ff_b = temp_b.user.userprofile
        self.ff_b.role = "firefighter"
        self.ff_b.station = self.station_b
        self.ff_b.save()

        # 3. Setup Report assigned to Station A
        self.report = ReportFactory(station=self.station_a, status="System Detected")

        self.url = reverse("sensors:mobilize_team", args=[self.report.id])

    def test_mobilize_success(self):
        """TC-3-001: Success path: FF mobilizes Team."""
        # Put FF A on duty
        DutyAssignmentFactory(
            firefighter=self.ff_a,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        self.client.login(username=self.ff_a.user.username, password="password123")
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "Confirmed")
        self.assertEqual(self.report.mobilized_team.count(), 1)

    def test_mobilize_unauthorized_station(self):
        """TC-3-002: 403 authorization check."""
        # FF B tries to mobilize Report A (different station)
        self.client.login(username=self.ff_b.user.username, password="password123")
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertIn("Unauthorized", response.json()["error"])

    def test_mobilize_no_one_on_duty(self):
        """TC-3-003: No active duties."""
        # No duty assignments created for Station A
        self.client.login(username=self.ff_a.user.username, password="password123")
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "No firefighters are currently on duty", response.json()["message"]
        )

    def test_mobilize_invalid_report(self):
        """Covers the except Report.DoesNotExist branch."""
        self.client.login(username=self.ff_a.user.username, password="password123")
        url = reverse("sensors:mobilize_team", args=[9999])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_mobilize_server_error(self):
        """Covers the general Exception branch."""
        # 1. Put FF A on duty so the view passes the 400 check
        DutyAssignmentFactory(
            firefighter=self.ff_a,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        self.client.login(username=self.ff_a.user.username, password="password123")

        # 2. Trigger error by making the DB call fail
        with patch("sensors.models.Report.save", side_effect=Exception("DB Failure")):
            response = self.client.post(self.url)
            self.assertEqual(response.status_code, 500)


class DutyViewTest(TestCase):
    def setUp(self):
        self.ff = UserProfileFactory(role="firefighter")
        self.client.login(username=self.ff.user.username, password="password123")
        self.url = reverse("sensors:duty")

    def test_duty_view_filters_correctly(self):
        """Covers the end_time__gte logic in the duty view."""
        # Past shift (should not show)
        DutyAssignmentFactory(
            firefighter=self.ff,
            start_time=timezone.now() - timedelta(hours=5),
            end_time=timezone.now() - timedelta(hours=1),
        )
        # Active shift (should show)
        DutyAssignmentFactory(
            firefighter=self.ff,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["my_schedule"]), 1)
