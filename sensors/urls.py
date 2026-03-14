from django.urls import path
from django.contrib.auth import views as auth_views
from .views import dashboard, auth, maintenances, reports, maps, sensors, duties, api
from . import utils
from django.contrib.auth.views import LoginView

app_name = "sensors"
urlpatterns = [
    # utils
    path("get-live-logs/", utils.get_live_logs, name="get_live_logs"),
    path("test-log/", api.test_log, name="test_log"),
    path("api/send-data/", api.receive_sensor_data, name="receive_data"),
    path(
        "update-location/<int:owner_id>/",
        api.update_location_from_link,
        name="update_location_link",
    ),
    # Home / Dashboard
    path("", dashboard.dashboard_view, name="home"),
    path("dashboard/", dashboard.dashboard_view, name="dashboard"),
    path(
        "sensors/delete/<int:sensor_id>/", dashboard.delete_sensor, name="delete_sensor"
    ),
    # 2. NEW: API for Public Dashboard Table (Humidity/Temp)
    path(
        "api/dashboard-data/",
        dashboard.get_dashboard_sensor_data,
        name="dashboard_data",
    ),
    # 3. NEW: API for AJAX Delete Button
    path(
        "api/delete-sensor/<int:sensor_id>/",
        dashboard.delete_sensor_ajax,
        name="delete_sensor_ajax",
    ),
    # Authentication & Profile
    path(
        "login/",
        LoginView.as_view(template_name="sensors/auth/login.html"),
        name="login",
    ),
    path("logout/", auth.logout_view, name="logout"),
    path("register/", auth.register, name="register"),
    path(
        "reset_password/",
        auth_views.PasswordResetView.as_view(
            template_name="sensors/auth/password_reset.html"
        ),
        name="password_reset",
    ),
    path(
        "reset_password_sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="sensors/auth/password_reset_sent.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="sensors/auth/password_reset_form.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset_password_complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="sensors/auth/password_reset_done.html"
        ),
        name="password_reset_complete",
    ),
    # User Profile
    path("profile/", auth.profile, name="profile"),
    path("change-password/", auth.change_password, name="change_password"),
    # Maintenance
    path("maintenance/", maintenances.maintenance_view, name="maintenance"),
    path(
        "maintenance/create/",
        maintenances.create_maintenance,
        name="maintenance_create",
    ),
    path(
        "maintenance/edit/<int:maintenance_id>/",
        maintenances.edit_maintenance,
        name="maintenance_edit",
    ),
    path(
        "maintenance/<int:maintenance_id>/",
        maintenances.maintenance_detail,
        name="maintenance_detail",
    ),
    path(
        "maintenance/delete/<int:maintenance_id>/",
        maintenances.delete_maintenance,
        name="delete_maintenance",
    ),
    # Reports
    path("reports/", reports.reports_view, name="reports"),
    path("reports/<int:report_id>/", reports.report_detail, name="report_detail"),
    path("reports/create/", reports.create_report, name="create_report"),
    path("reports/edit/<int:report_id>/", reports.edit_report, name="edit_report"),
    path(
        "reports/delete/<int:report_id>/", reports.delete_report, name="delete_report"
    ),
    # MAPS
    path("api/map-data/", maps.firefighter_map_data, name="map_data"),
    path("maps/", maps.maps, name="maps"),
    path(
        "api/update_station_coords/",
        maps.update_station_coordinates,
        name="update_station_coords",
    ),
    path("upload-layout/", maps.upload_layout, name="upload_layout"),
    path("api/edit-layout/", maps.edit_layout_ajax, name="edit_layout_ajax"),
    path(
        "delete-layout/<int:layout_id>/",
        maps.delete_layout_ajax,
        name="delete_layout_ajax",
    ),
    path(
        "api/get-victim-layout/<int:user_id>/",
        maps.get_victim_layout,
        name="get_victim_layout",
    ),
    # Sensors
    # Live Data API (The Website checks this every 2 seconds)
    path("api/live-data/", sensors.get_live_data, name="live_data"),
    # API Endpoints (These feed the maps)
    path("api/add-sensor/", sensors.add_sensor, name="add_sensor"),
    path(
        "api/update-sensor-pos/",
        sensors.update_sensor_position,
        name="update_sensor_pos",
    ),
    # Duties
    path("duty/", duties.duty, name="duty"),
    path("api/mobilize/<int:report_id>/", duties.mobilize_team, name="mobilize_team"),
]
