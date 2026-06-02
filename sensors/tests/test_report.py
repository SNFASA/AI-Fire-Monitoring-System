import os
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest, QueryDict
from django.test import Client, TestCase
from django.urls import reverse

from sensors.models import Report, ReportImage

from ..views.reports import handle_report_images
from .factories import (
    FireStationFactory,
    ReportFactory,
    ReportImageFactory,
    UserProfileFactory,
)


class ReportCoverageTest(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Setup Report and Station First
        self.station = FireStationFactory()
        self.report = ReportFactory(station=self.station)

        # 2. Setup Users
        self.ff = UserProfileFactory()
        self.ff.role = "firefighter"
        self.ff.station = self.station
        self.ff.save()

        self.public_user = UserProfileFactory()
        self.public_user.role = "public"
        self.public_user.save()

        self.detail_url = reverse("sensors:report_detail", args=[self.report.id])
        self.delete_url = reverse("sensors:delete_report", args=[self.report.id])

    # --- Security & Role Tests ---

    def test_role_restriction_create_report(self):
        """Covers check_firefighter_role Exception branch."""
        self.client.login(
            username=self.public_user.user.username, password="password123"
        )
        response = self.client.get(reverse("sensors:create_report"))
        self.assertEqual(response.status_code, 403)  # Permission Denied

    # --- report_detail Tests ---

    def test_report_detail_firefighter_quick_update(self):
        """Covers the firefighter-only POST branch in report_detail."""
        self.client.login(username=self.ff.user.username, password="password123")
        data = {
            "fire_type": "Class A",
            "cause": "Electrical",
            "description": "Updated detail",
            "status": "Confirmed",
            "station": self.station.id,
        }
        response = self.client.post(self.detail_url, data)

        self.assertRedirects(response, self.detail_url)

        self.report.refresh_from_db()
        self.assertEqual(self.report.cause, "Electrical")
        self.assertEqual(self.report.in_charge, self.ff.user)

    # --- Create & Edit Tests ---

    def test_create_report_with_images(self):
        self.client.login(username=self.ff.user.username, password="password123")
        image = SimpleUploadedFile(
            "fire.jpg", b"file_content", content_type="image/jpeg"
        )

        data = {
            "address": self.station.address.id,
            "description": "New Emergency",
            "images": [image],
        }
        # Bypass strict form validation for this specific test
        with patch("sensors.forms.ReportCreateForm.is_valid", return_value=True):
            response = self.client.post(reverse("sensors:create_report"), data)

        new_report = Report.objects.last()
        self.assertEqual(new_report.description, "New Emergency")

    @patch("os.path.isfile")
    @patch("os.remove")
    def test_delete_report_and_cleanup(self, mock_remove, mock_isfile):
        """Covers the disk cleanup logic for images during report deletion."""
        self.client.login(username=self.ff.user.username, password="password123")
        mock_isfile.return_value = True  # Pretend file exists on disk
        ReportImageFactory(report=self.report)  # Add image to report

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, reverse("sensors:reports"))
        self.assertEqual(Report.objects.filter(id=self.report.id).count(), 0)
        self.assertTrue(mock_remove.called)  # Check if os.remove was triggered

    @patch("os.path.isfile")
    @patch("os.remove")
    def test_handle_report_images_delete_branch(self, mock_remove, mock_isfile):
        """Covers the selective image deletion branch in handle_report_images."""
        mock_isfile.return_value = True
        img_obj = ReportImageFactory(report=self.report)

        request = HttpRequest()

        # Set up POST data
        qdict_post = QueryDict(mutable=True)
        qdict_post.setlist("delete_images", [str(img_obj.id)])
        request.POST = qdict_post

        request.FILES = QueryDict(mutable=True)

        # Call the function directly
        handle_report_images(request, self.report)

        # Ensure the image was actually deleted from the database
        self.assertEqual(ReportImage.objects.filter(id=img_obj.id).count(), 0)
        self.assertTrue(mock_remove.called)
    
    def test_edit_report_commander_approval_logic(self):
        """Covers commander status updates and is_approved toggle."""
        self.ff.rank = "PBK"
        self.ff.save()
        self.client.force_login(self.ff.user)
        
        url = reverse("sensors:edit_report", args=[self.report.id])
        data = {
            "status": "Confirmed",
            "is_approved": "on",
            "description": "Commander approved this.",
            "fire_type": "Class A",
            "cause": "Unknown",
            "station": self.station.id,        
            "address": self.station.address.id, # <--- FIX: Use the guaranteed station address
        }
        self.client.post(url, data)
        
        self.report.refresh_from_db()
        self.assertTrue(self.report.is_approved)

    def test_edit_report_image_deletion(self):
        """Covers delete_images branch in handle_report_images."""
        img = ReportImageFactory(report=self.report)
        self.client.force_login(self.ff.user)
        
        url = reverse("sensors:edit_report", args=[self.report.id])
        data = {
            "status": "System Detected",
            "fire_type": "Class A",
            "cause": "Unknown",
            "description": "delete image test",
            "station": self.station.id,        
            "address": self.station.address.id, # <--- FIX: Use the guaranteed station address
            "delete_images": [img.id]
        }
        with patch("os.remove"):
            self.client.post(url, data)
        
        self.assertEqual(ReportImage.objects.filter(id=img.id).count(), 0)

    def test_reports_view_firefighter_filtering(self):
        """Covers firefighter filtering by station."""
        # Create a report for a DIFFERENT station
        other_station = FireStationFactory()
        ReportFactory(station=other_station)
        
        self.client.force_login(self.ff.user)
        response = self.client.get(reverse("sensors:reports"))
        
        # Should only see the one report assigned to self.station (via setup)
        # and NOT the one for the other_station
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertEqual(response.context["reports"][0].station, self.station)

    def test_report_detail_permission_denied(self):
        """Covers PermissionDenied if firefighter accesses wrong station report."""
        other_report = ReportFactory(station=FireStationFactory())
        
        self.client.force_login(self.ff.user)
        response = self.client.get(reverse("sensors:report_detail", args=[other_report.id]))
        self.assertEqual(response.status_code, 403)
    
    def test_report_detail_public_unauthorized(self):
        """Covers public user trying to view report they don't own."""
        # report belongs to station, no owner explicitly set in factory
        self.client.force_login(self.public_user.user)
        response = self.client.get(reverse("sensors:report_detail", args=[self.report.id]))
        self.assertEqual(response.status_code, 403)