import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
station_id = "4"  # Match your target station channel block

test_payload = {
    "type": "fire_alert",
    "report_id": 999,
    "address": "Lot 123, Jalan Universiti, UTHM Parit Raja, Johor",
    "owner_name": "Syed Nabil Afifi",
    "owner_phone": "+6011-39771785",
    "lat": 1.8532,
    "lng": 103.0864,
    "timestamp": "2026-05-22 02:30:00",
}

async_to_sync(channel_layer.group_send)(f"station_{station_id}", test_payload)
print("🚀 [TEST ENGINE] Simulated emergency broadcast injected down channel array!")
