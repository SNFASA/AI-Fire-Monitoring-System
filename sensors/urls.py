from django.urls import path
from . import views
from django.contrib.auth.views import LoginView

urlpatterns = [
    # Home / Dashboard
    path('', views.dashboard, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Authentication
    path('login/', LoginView.as_view(template_name='sensors/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register, name='register'),
    
    # User Profile
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    
    # Maintenance
    path('maintenance/', views.maintenance, name='maintenance'),
    path('maintenance/<int:maintenance_id>/', views.maintenance_detail, name='maintenance_detail'),
    
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

    # API Endpoints (These feed the maps)
    path('api/add-sensor/', views.add_sensor, name='add_sensor'),
    path('api/update-sensor-pos/', views.update_sensor_position, name='update_sensor_pos'),
    
    # --- THIS LINE FIXES THE FIREFIGHTER MAP DOTS ---
    path('api/map-data/', views.firefighter_map_data, name='map_data'), 
    path('api/get-victim-layout/<int:user_id>/', views.get_victim_layout, name='get_victim_layout'),
]