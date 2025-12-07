from django.urls import path
from . import views

urlpatterns = [
    #API for ESP32 (The IoT Device sends data here)
    path('api/send-data/', views.receive_sensor_data, name='receive_data'),

    #Live Data API (The Website checks this every 2 seconds)
    path('api/live-data/', views.get_live_data, name='live_data'),

    # The user Dashboard (The Map and Table)
    path('dashboard/', views.dashboard, name='dashboard'),
]