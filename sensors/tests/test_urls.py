from django.contrib.auth import views as auth_views
from django.test import SimpleTestCase
from django.urls import resolve, reverse

from sensors.views import (
    api,
    auth,
    dashboard,
    duties,
    maintenances,
    maps,
    reports,
    sensors,
)


class TestUrls(SimpleTestCase):
    def test_home_url_resolves(self):
        url = reverse("sensors:home")
        self.assertEqual(resolve(url).func, dashboard.dashboard_view)

    def test_live_data_api_resolves(self):
        # This was the one causing the NoReverseMatch error!
        url = reverse("sensors:live_data")
        self.assertEqual(resolve(url).func, sensors.get_live_data)

    def test_register_url_resolves(self):
        url = reverse("sensors:register")
        self.assertEqual(resolve(url).func, auth.register)

    def test_map_data_url_resolves(self):
        url = reverse("sensors:map_data")
        self.assertEqual(resolve(url).func, maps.firefighter_map_data)

    def test_mobilize_team_url_resolves(self):
        url = reverse("sensors:mobilize_team", args=[1])
        self.assertEqual(resolve(url).func, duties.mobilize_team)

    def test_password_reset_url_resolves(self):
        url = reverse("sensors:password_reset")
        # Check for class-based views
        self.assertEqual(resolve(url).func.view_class, auth_views.PasswordResetView)
