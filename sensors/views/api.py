import json
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from ..utils import send_sms_broadcast, haversine
from ..models import Sensor, SensorDataLog, Report, FireStation, DutyAssignment, UserProfile
from ..logger import add_log
from ml_engine.predictor import FirePredictor

predictor = FirePredictor()


def test_log(request):
    add_log("\n[TEST] This is a test log entry.\n")
    return JsonResponse({"status": "Log added"})


# ==========================================
# 1. SMART DISPATCH (AI + LOCATION LOGIC)
# ==========================================
@csrf_exempt
def receive_sensor_data(request):
    """
    Receives JSON from Simulator -> Runs AI -> Finds Nearest ACTIVE Station -> Sends Alerts
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # 1. Parse Data
            methane = data.get("methane", 0)
            lpg = data.get("lpg", 0)
            co = data.get("co", 0)
            air_quality = data.get("air_quality", 0)
            flame_val = data.get("flame_val", 4095)
            dht22_temp = data.get("dht22_temp", 0)
            humidity = data.get("humidity", 0)
            sensor_id_raw = data.get("sensor_id")

            # 2. AI Prediction
            ml_result = predictor.predict(
                methane, lpg, co, air_quality, flame_val, dht22_temp, humidity
            )

            print(f"📡 [DATA] Sensor {sensor_id_raw} | Status: {ml_result}")
            add_log(f"[DATA] Sensor {sensor_id_raw}: {ml_result}")

            sensor = Sensor.objects.filter(id=sensor_id_raw).first() if sensor_id_raw else None

            if sensor:
                # 3. Save Log to Database
                SensorDataLog.objects.create(
                    sensor=sensor,
                    methane=methane,
                    lpg=lpg,
                    co=co,
                    air_quality=air_quality,
                    flame_val=flame_val,
                    dht22_temp=dht22_temp,
                    humidity=humidity,
                    status=ml_result,
                )

                # 4. FIRE ALERT LOGIC
                if ml_result == "Fire" and sensor.owner.address:
                    user_address = sensor.owner.address

                    # --- COORDINATE CHECK ---
                    # Explicitly check for None to allow 0.0 coordinates
                    # Inside receive_sensor_data where latitude is None:
                    if user_address.latitude is None or user_address.longitude is None:
                        if sensor.owner.phone_number:
                            # Construct a link to your new view
                            update_url = f"https://yourdomain.com/update-location/{sensor.owner.id}/"
                            
                            missing_coord_msg = (
                                f"🚨 EMERGENCY: Fire detected at your property!\n\n"
                                f"We don't have your GPS coordinates. Click here to share your location "
                                f"so we can dispatch the fire station: {update_url}"
                            )
                            send_sms_broadcast([sensor.owner.phone_number], missing_coord_msg)
                        return HttpResponse("1")

                    # Deduplication: Don't spam if report is already active
                    active_report = Report.objects.filter(
                        address=user_address,
                        status__in=["System Detected", "Confirmed"],
                    ).first()

                    if active_report:
                        active_report.save()  # Update timestamp
                        print(f"ℹ️ Alert updated for Report #{active_report.id}")
                    else:
                        # --- FIND NEAREST STATION WITH ACTIVE STAFF ---
                        stations = FireStation.objects.all()
                        station_distances = []

                        # Calculate distances to all stations
                        for station in stations:
                            # Explicit check for station coordinates too
                            if (station.address.latitude is not None and 
                                station.address.longitude is not None):
                                
                                dist = haversine(
                                    user_address.latitude,
                                    user_address.longitude,
                                    station.address.latitude,
                                    station.address.longitude,
                                )
                                station_distances.append((dist, station))

                        # Sort by Nearest
                        station_distances.sort(key=lambda x: x[0])

                        target_station = None
                        target_staff = []
                        now = timezone.now()

                        # Loop to find the first station that has people ON DUTY
                        for dist, station in station_distances:
                            on_duty = DutyAssignment.objects.filter(
                                firefighter__station=station,
                                start_time__lte=now,
                                end_time__gte=now,
                                is_active=True,
                            ).select_related("firefighter")

                            if on_duty.exists():
                                target_station = station
                                target_staff = on_duty
                                print(f"✅ Active Station Found: {station.name} ({dist:.2f}km)")
                                break

                        # Fallback: Nearest station if no one is on duty
                        if not target_station and station_distances:
                            target_station = station_distances[0][1]
                            print(f"⚠️ No active staff found. Defaulting to nearest: {target_station.name}")

                        if target_station:
                            # 5. Create Report
                            new_report = Report.objects.create(
                                status="System Detected",
                                address=user_address,
                                trigger_sensor=sensor,
                                trigger_reading=dht22_temp,
                                trigger_gas_level=max(methane, lpg, co),
                                trigger_temperature=dht22_temp,
                                station=target_station,
                                description=f"Automated Alert: Fire at {user_address.street}.",
                            )

                            # 6. SEND ALERTS (WebSockets and WhatsApp)
                            channel_layer = get_channel_layer()
                            payload = {
                                "type": "fire_alert",
                                "report_id": new_report.id,
                                "address": f"{user_address.street}, {user_address.city}",
                                "owner_name": sensor.owner.user.username,
                                "owner_phone": sensor.owner.phone_number,
                                "lat": user_address.latitude,
                                "lng": user_address.longitude,
                                "timestamp": str(new_report.timestamp),
                            }

                            async_to_sync(channel_layer.group_send)(f"station_{target_station.id}", payload)
                            async_to_sync(channel_layer.group_send)("station_all", payload)

                            # WhatsApp to Firefighters
                            phone_list = [d.firefighter.phone_number for d in target_staff if d.firefighter.phone_number]
                            if phone_list:
                                msg = f"FIRE ALERT! Loc: {user_address.street}. Station {target_station.name} mobilized."
                                send_sms_broadcast(phone_list, msg)

                            # WhatsApp to Owner
                            if sensor.owner.phone_number:
                                owner_msg = f"URGENT: Fire detected at your property ({user_address.street}). Station {target_station.name} has been notified."
                                send_sms_broadcast([sensor.owner.phone_number], owner_msg)

            return HttpResponse("1" if ml_result != "Safe" else "0")

        except Exception as e:
            print(f"❌ Error in receive_sensor_data: {e}")
            return HttpResponse("0")
    return HttpResponse("0", status=405)

def update_location_from_link(request, owner_id):
    # Fetch the owner; if they don't exist, 404
    owner = get_object_or_404(Sensor, id=owner_id)
    
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            lat = data.get("lat")
            lng = data.get("lng")
            
            if lat is not None and lng is not None:
                # Update the related Address model
                address = owner.address
                address.latitude = lat
                address.longitude = lng
                address.save()
                return JsonResponse({"status": "success", "message": "Location updated successfully!"})
                
            return JsonResponse({"status": "error", "message": "Invalid coordinates."}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    # For GET requests, show the button page
    return render(request, "update_location.html", {"owner": owner})