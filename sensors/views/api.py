import json
from django.shortcuts import render, get_object_or_404
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from ..utils import send_sms_broadcast, haversine
from ..models import (
    Sensor,
    SensorDataLog,
    Report,
    FireStation,
    DutyAssignment,
    UserProfile,
)
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

            # Optimization: select_related to get owner and address in one hit
            sensor = (
                Sensor.objects.select_related("owner", "owner__address", "owner__user")
                .filter(id=sensor_id_raw)
                .first()
            )

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

                # 4. FIRE/GAS ALERT LOGIC
                if ml_result in ["Fire", "gas leak"] and sensor.owner.address:
                    user_address = sensor.owner.address

                    # --- COORDINATE CHECK (SECURE) ---
                    if user_address.latitude is None or user_address.longitude is None:
                        if sensor.owner.phone_number:
                            # Generate secure, time-limited token
                            signer = TimestampSigner()
                            signed_id = signer.sign(str(sensor.owner.id))

                            # Build dynamic absolute URL
                            relative_url = reverse(
                                "sensors:update_location_from_link", args=[signed_id]
                            )
                            update_url = request.build_absolute_uri(relative_url)

                            missing_coord_msg = (
                                f"🚨 EMERGENCY: {ml_result.upper()} detected at your property!\n\n"
                                f"We don't have your GPS coordinates. Click here to share your location "
                                f"instantly so BOMBA can be dispatched: {update_url}"
                            )

                            send_sms_broadcast(
                                [sensor.owner.phone_number], missing_coord_msg
                            )

                        return HttpResponse("1")  # Alert triggered but waiting for GPS

                    # 5. Deduplication: Don't spam if report is already active
                    active_report = Report.objects.filter(
                        address=user_address,
                        status__in=["System Detected", "Confirmed"],
                    ).first()

                    if active_report:
                        active_report.save()  # Updates 'updated_at' timestamp
                        print(f"ℹ️ Alert updated for Report #{active_report.id}")
                    else:
                        # --- FIND NEAREST STATION WITH ACTIVE STAFF ---
                        # Fetch stations and their addresses
                        stations = FireStation.objects.select_related("address").all()
                        station_distances = []

                        for station in stations:
                            if (
                                station.address.latitude is not None
                                and station.address.longitude is not None
                            ):
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

                        # Loop to find the first station with people ON DUTY
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
                                print(
                                    f"✅ Active Station Found: {station.name} ({dist:.2f}km)"
                                )
                                break

                        # Fallback: Nearest station if no one is on duty record
                        if not target_station and station_distances:
                            target_station = station_distances[0][1]
                            print(
                                f"⚠️ Defaulting to nearest station: {target_station.name}"
                            )

                        if target_station:
                            # 6. Create Official Report
                            new_report = Report.objects.create(
                                status="System Detected",
                                address=user_address,
                                trigger_sensor=sensor,
                                trigger_reading=dht22_temp,
                                trigger_gas_level=max(methane, lpg, co),
                                trigger_temperature=dht22_temp,
                                station=target_station,
                                description=f"Automated AI Alert: {ml_result} at {user_address.street}.",
                            )

                            # 7. SEND REAL-TIME ALERTS (WebSockets)
                            channel_layer = get_channel_layer()
                            payload = {
                                "type": "fire_alert",
                                "report_id": new_report.id,
                                "address": f"{user_address.street}, {user_address.city}",
                                "owner_name": sensor.owner.user.username,
                                "owner_phone": sensor.owner.phone_number,
                                "lat": float(user_address.latitude),
                                "lng": float(user_address.longitude),
                                "timestamp": timezone.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                ),
                            }

                            # Notify specific station group and global group
                            async_to_sync(channel_layer.group_send)(
                                f"station_{target_station.id}", payload
                            )
                            async_to_sync(channel_layer.group_send)(
                                "station_all", payload
                            )

                            # 8. WHATSAPP NOTIFICATIONS
                            # Alert Firefighters
                            staff_phones = [
                                d.firefighter.phone_number
                                for d in target_staff
                                if d.firefighter.phone_number
                            ]
                            if staff_phones:
                                firefighter_msg = f"🔥 FIRE ALERT! Loc: {user_address.street}. Station {target_station.name} mobilized."
                                send_sms_broadcast(staff_phones, firefighter_msg)

                            # Alert Property Owner
                            if sensor.owner.phone_number:
                                owner_msg = f"URGENT: {ml_result} detected at your property ({user_address.street}). {target_station.name} has been notified."
                                send_sms_broadcast(
                                    [sensor.owner.phone_number], owner_msg
                                )

            return HttpResponse("1" if ml_result != "Safe" else "0")

        except Exception as e:
            print(f"❌ Error in receive_sensor_data: {e}")
            return HttpResponse("0")

    return HttpResponse("0", status=405)


def update_location_from_link(request, signed_id):
    """
    Updates location using a signed token to prevent ID spoofing.
    """
    signer = TimestampSigner()
    try:
        # 1. Unsign the ID. This fails if the token was tampered with.
        # Max_age ensures the emergency link expires after 30 minutes.
        owner_id = signer.unsign(signed_id, max_age=1800)
    except (SignatureExpired, BadSignature):
        return render(
            request,
            "sensors/error.html",
            {"message": "This emergency link has expired or is invalid."},
        )

    owner_profile = get_object_or_404(UserProfile, id=owner_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            lat, lng = data.get("lat"), data.get("lng")

            if lat and lng and owner_profile.address:
                address = owner_profile.address
                address.latitude, address.longitude = lat, lng
                address.save()
                return JsonResponse(
                    {"status": "success", "message": "Emergency location updated!"}
                )

            return JsonResponse(
                {"status": "error", "message": "Invalid data."}, status=400
            )
        except Exception:
            return JsonResponse(
                {"status": "error", "message": "Server error."}, status=500
            )

    return render(
        request,
        "sensors/update_location.html",
        {"owner": owner_profile, "token": signed_id},
    )
