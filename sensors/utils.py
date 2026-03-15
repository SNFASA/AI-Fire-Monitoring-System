import json
import math
from django.conf import settings
from django.utils import timezone
from twilio.rest import Client
from .models import FireStation
from django.http import JsonResponse
from datetime import timedelta
from .logger import get_logs


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
    status = last_log.status
    if status == "GasLeak":
        return "gas leak"
    return status
