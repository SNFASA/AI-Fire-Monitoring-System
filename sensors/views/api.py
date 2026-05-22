import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from ml_engine.predictor import FirePredictor
from sensors.filters import SensorFilter

from ..logger import add_log
from ..models import (
    Address,
    DutyAssignment,
    FireStation,
    Report,
    Sensor,
    SensorDataLog,
    UserProfile,
)
from ..utils import haversine, send_sms_broadcast

predictor = FirePredictor()


def normalize_ml_result(result):
    """
    Standardizes ML output for consistency across the DB and UI.
    """
    if result is None:
        return "Safe"

    normalized = str(result).strip().lower()
    if normalized == "fire":
        return "Fire"
    if normalized in ["gas leak", "gasleak"]:
        return "Gas Leak"
    if normalized == "warning":
        return "Warning"

    return "Safe"


def test_log(request):
    add_log("\n[TEST] This is a test log entry.\n")
    return JsonResponse({"status": "Log added"})


# ==========================================
# 1. SMART DISPATCH (AI + LOCATION LOGIC)
# ==========================================
@csrf_exempt
def receive_sensor_data(request):
    """
    Receives JSON -> Runs AI -> Triages Result -> Optimized Dispatch -> Alerts
    """
    if request.method != "POST":
        return HttpResponse("0", status=405)

    if not request.body:
        return HttpResponse("0")

    try:
        # 1. Parse Data
        data = json.loads(request.body)
        methane = data.get("methane", 0)
        lpg = data.get("lpg", 0)
        co = data.get("co", 0)
        air_quality = data.get("air_quality", 0)
        flame_val = data.get("flame_val", 4095)
        dht22_temp = data.get("dht22_temp", 0)
        humidity = data.get("humidity", 0)
        sensor_id_raw = data.get("sensor_id")

        # 2. AI Prediction
        raw_ml_result = predictor.predict(
            methane, lpg, co, air_quality, flame_val, dht22_temp, humidity
        )
        ml_result = normalize_ml_result(raw_ml_result)

        print(f"📡 [DATA] Sensor {sensor_id_raw} | Status: {ml_result}")
        add_log(f"[DATA] Sensor {sensor_id_raw}: {ml_result}")

        # Fetch Sensor with optimized joins
        sensor = (
            Sensor.objects.select_related("owner", "owner__address", "owner__user")
            .filter(id=sensor_id_raw)
            .first()
        )

        if not sensor:
            return JsonResponse({"error": "Sensor ID not found"}, status=404)

        # 3. Save Log with Timezone Support
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
            timestamp=timezone.now(),
        )
        sensor.last_status = ml_result
        sensor.save(update_fields=["last_status", "updated"])
        # 4. ALERT TRIAGE LOGIC
        if ml_result in ["Fire", "Gas Leak", "Warning"] and sensor.owner.address:
            user_address = sensor.owner.address

            # --- A. SECURE COORDINATE CHECK ---
            if user_address.latitude is None or user_address.longitude is None:
                if sensor.owner.phone_number:
                    signer = TimestampSigner()
                    signed_id = signer.sign(str(sensor.owner.id))
                    relative_url = reverse(
                        "sensors:update_location_link", args=[signed_id]
                    )
                    update_url = request.build_absolute_uri(relative_url)

                    msg = (
                        f"🚨 EMERGENCY: {ml_result.upper()} detected!\n\n"
                        f"We need your GPS coordinates to dispatch BOMBA. "
                        f"Click here: {update_url}"
                    )
                    send_sms_broadcast([sensor.owner.phone_number], msg)

                # FIX: Even if they have no GPS, we MUST ring the physical buzzer!
                override_alarm = (
                    True if ml_result in ["Fire", "Warning", "Gas Leak"] else False
                )
                return JsonResponse({"fire_override": override_alarm})

            # --- B. DEDUPLICATION ---
            active_report = Report.objects.filter(
                address=user_address,
                status__in=["System Detected", "Confirmed"],
            ).first()

            if active_report:
                active_report.save()  # Triggers auto-now updated_at
                print(f"ℹ️ Alert updated for Report #{active_report.id}")

            # --- C. BRANCH: FIRE DISPATCH ---
            elif ml_result == "Fire":
                # Find candidate stations
                stations = FireStation.objects.select_related("address").all()
                station_distances = []
                for station in stations:
                    if station.address.latitude and station.address.longitude:
                        dist = haversine(
                            user_address.latitude,
                            user_address.longitude,
                            station.address.latitude,
                            station.address.longitude,
                        )
                        station_distances.append((dist, station))

                station_distances.sort(key=lambda x: x[0])

                # Optimized: Single DB hit for all active staff in nearby stations
                now = timezone.now()
                active_staff_all = DutyAssignment.objects.filter(
                    firefighter__station__in=[s for d, s in station_distances],
                    start_time__lte=now,
                    end_time__gte=now,
                    is_active=True,
                ).select_related("firefighter", "firefighter__station")

                target_station = None
                target_staff = []

                for dist, station in station_distances:
                    staff = [
                        d
                        for d in active_staff_all
                        if d.firefighter.station_id == station.id
                    ]
                    if staff:
                        target_station = station
                        target_staff = staff
                        print(f"✅ Active Station Found: {station.name} ({dist:.2f}km)")
                        break

                # Fallback to nearest station regardless of duty logs
                if not target_station and station_distances:
                    target_station = station_distances[0][1]

                if target_station:
                    # Create Official Report
                    new_report = Report.objects.create(
                        status="System Detected",
                        address=user_address,
                        trigger_sensor=sensor,
                        trigger_reading=dht22_temp,
                        trigger_gas_level=max(methane, lpg, co),
                        trigger_temperature=dht22_temp,
                        station=target_station,
                        description=f"Automated AI Fire Alert at {user_address.street}.",
                    )

                    # WebSocket Notification
                    channel_layer = get_channel_layer()
                    payload = {
                        "type": "fire_alert",
                        "report_id": new_report.id,
                        "address": f"{user_address.street}, {user_address.city}",
                        "owner_name": sensor.owner.user.username,
                        "owner_phone": sensor.owner.phone_number,
                        "lat": float(user_address.latitude),
                        "lng": float(user_address.longitude),
                        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    async_to_sync(channel_layer.group_send)(
                        f"station_{target_station.id}", payload
                    )
                    async_to_sync(channel_layer.group_send)("station_all", payload)

                    # SMS Broadcast to Firefighters and Owner
                    staff_phones = [
                        d.firefighter.phone_number
                        for d in target_staff
                        if d.firefighter.phone_number
                    ]
                    if staff_phones:
                        send_sms_broadcast(
                            staff_phones,
                            f"🔥 FIRE ALERT! {user_address.street}. Station {target_station.name} mobilized.",
                        )

                    if sensor.owner.phone_number:
                        send_sms_broadcast(
                            [sensor.owner.phone_number],
                            f"URGENT: Fire detected at your property. Bomba mobilized.",
                        )

            # --- D. BRANCH: GAS LEAK (Owner-only Alert) ---
            elif ml_result == "Gas Leak":
                if sensor.owner.phone_number:
                    gas_msg = f"⚠️ GAS LEAK: High gas detected at {user_address.street}. Please ventilate and check your home."
                    send_sms_broadcast([sensor.owner.phone_number], gas_msg)
                print(f"☣️ Gas Leak Notification sent for Sensor {sensor_id_raw}")

        override_alarm = True if ml_result in ["Fire", "Warning", "Gas Leak"] else False

        # Send a 200 OK success response back with the override command
        return JsonResponse({"fire_override": override_alarm})

    except Exception as e:
        print(f"❌ Error in receive_sensor_data: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def update_location_from_link(request, signed_id):
    signer = TimestampSigner()
    try:
        owner_id = signer.unsign(signed_id, max_age=1800)
    except (SignatureExpired, BadSignature):
        return render(
            request, "sensors/error.html", {"message": "Invalid/Expired link."}
        )

    owner_profile = get_object_or_404(UserProfile, id=owner_id)

    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # 1. Clean extraction
            try:
                lat = float(data.get("lat"))
                lng = float(data.get("lng"))
            except (TypeError, ValueError):
                return JsonResponse(
                    {"status": "error", "message": "Invalid coordinates."}, status=400
                )

            # Check bounds
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                return JsonResponse(
                    {"status": "error", "message": "Out of bounds."}, status=400
                )

            # 2. Extract address fields once
            street = data.get("street", "").strip()
            city = data.get("city", "").strip()
            state = data.get("state", "").strip()
            postal_code = data.get("postal_code", "").strip()

            # 3. Update or Create logic
            if owner_profile.address:
                address = owner_profile.address
                address.latitude = lat
                address.longitude = lng

                # Only update text if we actually got a street name from the geocoder
                if street:
                    address.street = street
                    address.city = city
                    address.state = state
                    address.postal_code = postal_code
                address.save()
            else:
                # Create brand new address with fallbacks
                new_address = Address.objects.create(
                    latitude=lat,
                    longitude=lng,
                    street=street or "Emergency Location (GPS Pin)",
                    city=city or "Unknown",
                    state=state or "Unknown",
                    postal_code=postal_code or "00000",
                )
                owner_profile.address = new_address
                owner_profile.save()

            return JsonResponse({"status": "success", "message": "Location updated!"})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return render(
        request,
        "sensors/update_location.html",
        {"owner": owner_profile, "token": signed_id},
    )


def filters_sensor_view(request):
    # 1. ALWAYS fetch the real-time status, regardless of what filter is clicked
    latest_log = (
        SensorDataLog.objects.filter(sensor=OuterRef("pk"))
        .order_by("-timestamp")
        .values("status")[:1]
    )

    # 2. Attach (annotate) the current_status to the base queryset
    if request.user.is_authenticated:
        # Assuming owner__user is your path to the User model.
        # If your Sensor model uses 'owner' as UserProfile, this is correct.
        base_queryset = Sensor.objects.filter(owner__user=request.user).annotate(
            current_status=Subquery(latest_log)
        )
    else:
        base_queryset = Sensor.objects.annotate(current_status=Subquery(latest_log))

    # 3. Apply the filters (Search term, Layout, Status)
    sensor_filter = SensorFilter(request.GET, queryset=base_queryset)

    # 4. Extract the filtered data
    sensors_list = []
    for sensor in sensor_filter.qs:
        # Now 'current_status' will ALWAYS exist, even when clicking "All"
        status = getattr(sensor, "current_status", "Safe") or "Safe"

        sensors_list.append(
            {
                "id": sensor.id,
                "name": sensor.name,
                "status": status,
            }
        )

    return JsonResponse({"sensors": sensors_list})
