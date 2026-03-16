from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Using \d+ ensures only numeric station IDs are matched
    re_path(r"ws/alerts/(?P<station_id>\d+)/$", consumers.FireAlertConsumer.as_asgi()),
]
