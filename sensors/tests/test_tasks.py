from unittest.mock import MagicMock, patch

import pandas as pd
from django.contrib.gis.geos import Point
from django.test import TransactionTestCase  # <-- CHANGE THIS IMPORT

from sensors.models import CountryBoundary, SatelliteHotspot
from sensors.tasks import update_malaysia_hotspots


# Change the base class to TransactionTestCase
class AutomatedTaskLifecycleTests(TransactionTestCase):

    def setUp(self):
        # Create a mock bounding polygon geometry mapping out Malaysia region boundaries
        # Triangle covering parts of Johor for testing
        poly_geom = "MULTIPOLYGON(((102.0 1.0, 104.0 1.0, 103.0 2.0, 102.0 1.0)))"
        self.country = CountryBoundary.objects.create(name="Malaysia", geom=poly_geom)

    @patch("sensors.services.requests.get")
    def test_nasa_api_network_failure_exception(self, mock_get):
        """Covers request exception handling pathways when NASA servers drop connection."""
        mock_get.side_effect = Exception("Connection Timeout")

        # The task should catch the error internally via loggers and return a safe message string
        result = update_malaysia_hotspots()
        self.assertIn("Failed due to error", result)

    @patch("sensors.services.requests.get")
    @patch("sensors.services.process_hotspot_coverage")
    def test_hotspot_geospatial_containment_filtering(self, mock_coverage, mock_get):
        """Validates that entries falling inside Malaysia are created, outside are skipped."""
        mock_response = MagicMock()

        mock_response.text = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,instrument\n"
            "1.5,103.0,2026-05-22,0200,90,25.5,VIIR\n"  # Inside
            "5.0,115.0,2026-05-22,1430,40,12.0,VIIR\n"  # Outside
        )
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        mock_coverage.return_value = False

        # Execute target Celery sync task block
        update_malaysia_hotspots()

        # Database should verify only one persistent entry survived spatial containment profiling
        self.assertEqual(SatelliteHotspot.objects.count(), 1)

    @patch("sensors.services.fetch_and_filter_hotspots")
    # In test_tasks.py
    def test_update_malaysia_hotspots_success_message(self, mock_fetch):
        mock_fetch.return_value = "Successfully fetched and saved 2 new NASA hotspots! Triggered 0 station alerts."
        result = update_malaysia_hotspots()
        self.assertEqual(result, "Successfully fetched and saved 2 new NASA hotspots! Triggered 0 station alerts.")
    
    @patch("sensors.tasks.fetch_and_filter_hotspots")
    def test_update_malaysia_hotspots_task_crashes(self, mock_fetch):
        """Covers the critical failure branch where the task itself raises an Exception."""
        # Force the service function to crash
        mock_fetch.side_effect = Exception("System Crash")
        
        result = update_malaysia_hotspots()
        
        self.assertIn("Failed due to error: System Crash", result)