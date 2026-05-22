from unittest.mock import MagicMock, patch

from django.contrib.gis.geos import Point
from django.test import TransactionTestCase
from django.utils import timezone

from sensors.models import CountryBoundary, SatelliteHotspot
from sensors.services import fetch_and_filter_hotspots


class NasaFirmsServicesTests(TransactionTestCase):

    def setUp(self):
        # 1. Create a mock Malaysia boundary (A simple square covering lat 1-4, lon 101-104)
        poly_geom = (
            "MULTIPOLYGON(((101.0 1.0, 104.0 1.0, 104.0 4.0, 101.0 4.0, 101.0 1.0)))"
        )
        self.malaysia = CountryBoundary.objects.create(name="Malaysia", geom=poly_geom)

    def test_missing_country_boundary_aborts(self):
        """Ensure the script safely aborts if the Malaysia geometry is missing from the database."""
        self.malaysia.delete()  # Remove the boundary

        result = fetch_and_filter_hotspots()

        self.assertEqual(result, "Error: Malaysia boundary not loaded in database.")
        self.assertEqual(SatelliteHotspot.objects.count(), 0)

    @patch("sensors.services.requests.get")
    def test_network_timeout_skips_gracefully(self, mock_get):
        """Ensure that if the NASA API drops connection, the script skips to the next source instead of crashing."""
        import requests

        # Force the mock to throw a connection error when called
        mock_get.side_effect = requests.exceptions.ReadTimeout("NASA API Down")

        result = fetch_and_filter_hotspots()

        # It should complete the loop and return the standard empty success message
        self.assertEqual(
            result, "NASA connected successfully, but no new hotspots to add."
        )
        self.assertEqual(SatelliteHotspot.objects.count(), 0)

    @patch("sensors.services.process_hotspot_coverage")
    @patch("sensors.services.requests.get")
    def test_successful_fetch_filter_and_duplicate_prevention(
        self, mock_get, mock_process
    ):
        """Verifies parsing CSV, geospatial filtering, duplicate signature blocking, and saving."""

        # 1. Setup the Mock CSV Response from NASA
        # Point A: Inside Malaysia (102.0, 2.0)
        # Point B: Outside Malaysia (115.0, 5.0)
        mock_response = MagicMock()
        mock_response.text = (
            "latitude,longitude,acq_date,acq_time,confidence,frp,instrument,bright_ti4\n"
            "2.0,102.0,2026-05-23,0400,high,30.5,VIIR,330.0\n"  # Valid & Inside
            "5.0,115.0,2026-05-23,1230,low,10.0,VIIR,300.0\n"  # Outside (Should be filtered out)
        )
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # Assume our internal process coverage function triggers an alert for valid points
        mock_process.return_value = True

        # --- FIRST RUN: Should fetch and create 1 new hotspot ---
        result_1 = fetch_and_filter_hotspots()

        self.assertTrue(result_1.startswith("Successfully fetched and saved"))

        # FIX 1: Change '4' to '1' because the cross-satellite deduplication blocked the other 3!
        self.assertIn("1 new NASA hotspots", result_1)
        self.assertEqual(SatelliteHotspot.objects.count(), 1)

        # --- SECOND RUN: Should block everything due to duplicate signatures ---
        # The exact same CSV payload is processed again
        result_2 = fetch_and_filter_hotspots()

        self.assertEqual(
            result_2, "NASA connected successfully, but no new hotspots to add."
        )

        # FIX 2: The database count should REMAIN 1, proving secondary runs were completely ignored
        self.assertEqual(SatelliteHotspot.objects.count(), 1)
