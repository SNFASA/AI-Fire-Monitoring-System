from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.contrib.auth.views import LoginView

urlpatterns = [
    # Home / Dashboard
    path('', views.dashboard, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('get-live-logs/', views.get_live_logs, name='get_live_logs'),
    path('test-log/', views.test_log, name='test_log'),
    
    # Authentication
    path('login/', LoginView.as_view(template_name='sensors/auth/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    path('reset_password/', 
        auth_views.PasswordResetView.as_view(template_name="sensors/auth/password_reset.html"), 
        name='password_reset'),
    path('reset_password_sent/', 
         auth_views.PasswordResetDoneView.as_view(template_name="sensors/auth/password_reset_sent.html"), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name="sensors/auth/password_reset_form.html"), 
         name='password_reset_confirm'),
    path('reset_password_complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name="sensors/auth/password_reset_done.html"), 
         name='password_reset_complete'),
    
    # User Profile
    path('profile/', views.profile, name='profile'),
    path('duty/', views.duty, name='duty'),
    path('change-password/', views.change_password, name='change_password'),
    
    # Maintenance
    path('maintenance/', views.maintenance, name='maintenance'),
    path('maintenance/create/', views.create_maintenance, name='maintenance_create'),
    path('maintenance/edit/<int:maintenance_id>/', views.edit_maintenance, name='maintenance_edit'),
    path('maintenance/<int:maintenance_id>/', views.maintenance_detail, name='maintenance_detail'),
    path('maintenance/delete/<int:maintenance_id>/', views.delete_maintenance, name='delete_maintenance'),
    
    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/<int:report_id>/', views.report_detail, name='report_detail'),
    path('reports/create/', views.create_report, name='create_report'),
    
    # API for ESP32 (The IoT Device sends data here)
    path('api/send-data/', views.receive_sensor_data, name='receive_data'),

    # Live Data API (The Website checks this every 2 seconds)
    path('api/live-data/', views.get_live_data, name='live_data'),
    
    # Page Views
    path('maps/', views.maps, name='maps'),
    path('upload-layout/', views.upload_layout, name='upload_layout'),
    path('api/edit-layout/', views.edit_layout_ajax, name='edit_layout_ajax'),
    path('delete-layout/<int:layout_id>/', views.delete_layout_ajax, name='delete_layout_ajax'),
    path('sensors/delete/<int:sensor_id>/', views.delete_sensor, name='delete_sensor'),

    # API Endpoints (These feed the maps)
    path('api/add-sensor/', views.add_sensor, name='add_sensor'),
    path('api/update-sensor-pos/', views.update_sensor_position, name='update_sensor_pos'),
    
    # --- THIS LINE FIXES THE FIREFIGHTER MAP DOTS ---
    path('api/map-data/', views.firefighter_map_data, name='map_data'), 
    path('api/get-victim-layout/<int:user_id>/', views.get_victim_layout, name='get_victim_layout'),
    
    # 1. Existing Terminal Log URL (For Firefighters)
    path('get-live-logs/', views.get_live_logs, name='get_live_logs'),

    # 2. NEW: API for Public Dashboard Table (Humidity/Temp)
    path('api/dashboard-data/', views.get_dashboard_sensor_data, name='dashboard_data'),
    
    # 3. NEW: API for AJAX Delete Button
    path('api/delete-sensor/<int:sensor_id>/', views.delete_sensor_ajax, name='delete_sensor_ajax'),
    path('api/dashboard-data/', views.get_dashboard_sensor_data, name='dashboard_data'),
    path('api/delete-sensor/<int:sensor_id>/', views.delete_sensor_ajax, name='delete_sensor_ajax'),
    
]