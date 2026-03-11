# sensors/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # FIX: Use .as_asgi() for Consumers, NOT .as_view()
    re_path(r"ws/alerts/(?P<station_id>\w+)/$", consumers.FireAlertConsumer.as_asgi()),
]
