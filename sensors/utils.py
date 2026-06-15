import json
import math
from datetime import timedelta
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from twilio.rest import Client

from .logger import get_logs
from .models import Address, FireStation, Report


def get_live_logs(request):
    """Returns system logs for the terminal UI"""
    return JsonResponse({"logs": get_logs()})


def haversine(lat1, lon1, lat2, lon2):
    r_earth = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) * math.sin(d_lat / 2) + math.cos(
        math.radians(lat1)
    ) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) * math.sin(d_lon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_earth * c


def find_nearest_station(victim_lat, victim_lng):
    stations = FireStation.objects.all()
    nearest_station = None
    min_dist = float("inf")

    for station in stations:
        if station.address.latitude and station.address.longitude:
            dist = haversine(
                victim_lat,
                victim_lng,
                station.address.latitude,
                station.address.longitude,
            )
            if dist < min_dist:
                min_dist = dist
                nearest_station = station
    return nearest_station


def send_telegram_broadcast(chat_ids, message_text):
    """
    Blasts an emergency alert to a list of Telegram Chat IDs.
    """
    print("--- INITIATING TELEGRAM BROADCAST ---")
    
    # Grab the token from your Django settings
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN missing in settings.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for chat_id in chat_ids:
        # Skip if the user hasn't linked their Telegram yet
        if not chat_id:
            continue

        try:
            payload = {
                "chat_id": str(chat_id).strip(),
                "text": message_text,
                "parse_mode": "HTML" # Allows us to use <b>bold</b> and <i>italics</i> in alerts
            }
            
            # Send the request directly to Telegram's servers
            response = requests.post(url, json=payload, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ Telegram Sent to Chat ID: {chat_id}")
            else:
                print(f"❌ Telegram Failed for {chat_id}: {response.text}")
                
        except Exception as e:
            print(f"❌ Telegram Request Failed: {e}")
            
    print("--------------------------------")


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_sensor_status(sensor):
    """Determines if a sensor is Safe, Fire, Warning, or Offline"""
    last_log = sensor.readings.order_by("-timestamp").first()

    # Offline Check (No data for 5 minutes)
    if not last_log:
        return "Offline"
    if timezone.now() - last_log.timestamp > timedelta(minutes=5):
        return "Offline"

    # Return Status (Normalize 'GasLeak')
    raw_status = last_log.status or ""
    status = raw_status.strip()
    if status.replace(" ", "").lower() == "gasleak":
        return "Gas Leak"

    time_threshold = timezone.now() - timedelta(minutes=5)
    if sensor.updated < time_threshold:
        return "Offline"
     
    return status, sensor.last_status


def process_hotspot_coverage(hotspot):
    """
    Checks if a newly saved SatelliteHotspot falls within any Fire Station's coverage.
    If yes, generates an Address and a Report, then triggers a flat WebSocket alert.
    """
    # Extract lat/lon from the GeoDjango PointField
    fire_lat = hotspot.location.y
    fire_lon = hotspot.location.x

    # Optimized query to fetch stations and their linked addresses
    stations = FireStation.objects.select_related("address").all()

    for station in stations:
        # Safety check: skip stations without proper address coordinates
        if (
            not hasattr(station, "address")
            or station.address.latitude is None
            or station.address.longitude is None
        ):
            continue

        # Convert to radians for Haversine math
        lat1, lon1, lat2, lon2 = map(
            math.radians,
            [fire_lat, fire_lon, station.address.latitude, station.address.longitude],
        )

        # Calculate great-circle distance
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance = c * 6371000  # Earth radius in meters

        # Calculate radius from square meters
        coverage_radius = math.sqrt(station.cover_area_sqm / math.pi)

        if distance <= coverage_radius:
            # FIX 1: Create an Address record to securely store the fire coordinates
            wildfire_address = Address.objects.create(
                street="Satellite Detected Hotspot Area",
                city="Wildfire Zone",
                state=station.address.state,
                postal_code=station.address.postal_code,
                latitude=fire_lat,
                longitude=fire_lon,
            )

            # 2. Create the Official Report using valid model fields
            report = Report.objects.create(
                status="System Detected",
                address=wildfire_address,
                station=station,
                description=(
                    f"Automated Satellite Wildfire Alert.\n"
                    f"Thermal Brightness: {hotspot.brightness}K\n"
                    f"Fire Radiative Power (FRP): {hotspot.frp} MW"
                ),
                fire_type="Wildfire / Bushfire",
            )

            try:
                channel_layer = get_channel_layer()
                payload = {
                    "type": "fire_alert",
                    "report_id": report.id,
                    "address": f"{wildfire_address.street} ({station.address.city})",
                    "owner_name": "SATELLITE_SYSTEM",
                    "lat": float(fire_lat),
                    "lng": float(fire_lon),
                    "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

                # Broadcast to both the specific station group and the unified general dashboard
                async_to_sync(channel_layer.group_send)(
                    f"station_{station.id}", payload
                )
                async_to_sync(channel_layer.group_send)("station_all", payload)

                print(
                    f"📡 [SATELLITE TASK] Dispatched alert for Report #{report.id} to Station {station.name}"
                )
            except Exception as e:
                print(f"❌ WebSocket Error for Station {station.id}: {e}")

            return True  # Successfully matched and alerted

    return False  # No match found
