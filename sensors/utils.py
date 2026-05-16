import json
import math
from django.conf import settings
from django.utils import timezone
from twilio.rest import Client
from .models import FireStation, Report
from django.http import JsonResponse
from datetime import timedelta
from .logger import get_logs
import math
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync



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


def send_sms_broadcast(phone_numbers, message_text):
    print("--- INITIATING WHATSAPP BROADCAST ---")
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        # Prepare Template Variables
        if "Loc:" in message_text:
            clean_location = message_text.split("Loc:")[1].split(".")[0].strip()
        else:
            clean_location = "Unknown Location"

        current_time = timezone.now().strftime("%I:%M %p")

        # Send the raw dictionary
        content_vars = json.dumps({"1": clean_location, "2": current_time})

        for number in phone_numbers:
            if not number:
                continue

            clean_num = str(number).strip()
            if clean_num.startswith("whatsapp:"):
                formatted_num = clean_num
            elif clean_num.startswith("+"):
                formatted_num = f"whatsapp:{clean_num}"
            elif clean_num.startswith("60") and len(clean_num) > 9:
                formatted_num = f"whatsapp:+{clean_num}"
            elif clean_num.startswith("0"):
                formatted_num = f"whatsapp:+60{clean_num[1:]}"
            else:
                formatted_num = f"whatsapp:+60{clean_num}"

            print(f"Sending WhatsApp to {formatted_num}...")
            msg = client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=formatted_num,
                content_sid=settings.TWILIO_CONTENT_SID,
                content_variables=content_vars,
            )
            print(f"✅ WhatsApp Sent! SID: {msg.sid}")

    except Exception as e:
        print(f"❌ WhatsApp Failed: {e}")
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

    return status

def process_hotspot_coverage(hotspot):
    """
    Checks if a newly saved SatelliteHotspot falls within any Fire Station's coverage.
    If yes, generates a Report and triggers a WebSocket alert.
    """
    # Extract lat/lon from the GeoDjango PointField
    fire_lat = hotspot.location.y
    fire_lon = hotspot.location.x

    # Optimized query to fetch stations and their linked addresses
    stations = FireStation.objects.select_related('address').all()
    
    for station in stations:
        # Safety check: skip stations without proper address coordinates
        if not hasattr(station, 'address') or station.address.latitude is None or station.address.longitude is None:
            continue

        # Convert to radians for Haversine math
        lat1, lon1, lat2, lon2 = map(
            math.radians, 
            [fire_lat, fire_lon, station.address.latitude, station.address.longitude]
        )
        
        # Calculate great-circle distance
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance = c * 6371000  # Earth radius in meters
        
        # Calculate radius from square meters
        coverage_radius = math.sqrt(station.cover_area_sqm / math.pi)
        
        if distance <= coverage_radius:
            # 1. Create the Official Report
            report = Report.objects.create(
                station=station,
                latitude=fire_lat,
                longitude=fire_lon,
                status="System Detected"
            )
            
            # 2. Trigger WebSocket Alert
            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"station_{station.id}",
                    {
                        "type": "fire_alert",
                        "data": {
                            "report_id": report.id,
                            "latitude": report.latitude,
                            "longitude": report.longitude,
                            "status": report.status,
                            "station_name": station.name,
                            # Sending temperature/intensity directly to the dashboard!
                            "brightness": hotspot.brightness, 
                            "frp": hotspot.frp               
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket Error for Station {station.id}: {e}")
                
            return True # Successfully matched and alerted
            
    return False # No match found