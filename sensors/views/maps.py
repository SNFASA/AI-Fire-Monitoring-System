import json
import math
from datetime import timedelta

import pytz
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone  # KEEP THIS
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST

from sensors.services import fetch_and_filter_hotspots

from ..forms import HouseLayoutForm

# Local Imports
from ..models import FireStation, Houselayout, SatelliteHotspot, Sensor, UserProfile
from ..utils import get_sensor_status

# ==========================================
# 3. MAP DATA
# ==========================================
@login_required
def firefighter_map_data(request):
    """Returns map data, filtering out users with NULL coordinates"""
    if (
        not hasattr(request.user, "userprofile")
        or request.user.userprofile.role != "firefighter"
    ):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    data = []
    users = UserProfile.objects.filter(role="public").select_related("address")

    for profile in users:
        if (
            profile.address
            and profile.address.latitude is not None
            and profile.address.longitude is not None
        ):
            sensors = profile.sensors.all()
            house_status = "Safe"
            has_offline = False

            for s in sensors:
                s_status = get_sensor_status(s)
                
                # Priority 1: Fire overrides everything
                if s_status == "Fire":
                    house_status = "Fire"
                    break
                    
                # Priority 2: Gas Leak or Warning
                elif s_status in ["Gas Leak", "Warning"] and house_status != "Fire":
                    house_status = s_status
                    
                # Priority 3: Offline tracking
                elif s_status == "Offline":
                    has_offline = True

            # If no active emergencies are found, but a sensor is dead, mark house as Offline
            if house_status == "Safe" and has_offline and sensors.exists():
                house_status = "Offline"

            data.append(
                {
                    "id": profile.user.id,
                    "owner": profile.user.username,
                    "lat": profile.address.latitude,
                    "lng": profile.address.longitude,
                    "status": house_status, # This will now accurately pass "Warning" or "Gas Leak"
                }
            )

    return JsonResponse({"houses": data})


# ==========================================
# 4. MAPS view
# ==========================================
@login_required(login_url="login")
def maps(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        return render(request, "sensors/maps.html", {"role": "unknown"})

    context = {"role": user_profile.role, "user_profile": user_profile}

    # --- PUBLIC ROLE ---
    if user_profile.role == "public":
        user_layouts = Houselayout.objects.filter(user=request.user).order_by("id")
        selected_layout_id = request.GET.get("layout_id")
        current_layout = (
            user_layouts.filter(id=selected_layout_id).first()
            if selected_layout_id
            else user_layouts.first()
        )
        context.update(
            {
                "layouts": user_layouts,
                "current_layout": current_layout,
                "sensors": (
                    Sensor.objects.filter(owner=user_profile, layout=current_layout)
                    if current_layout
                    else []
                ),
            }
        )

    # --- FIREFIGHTER ROLE ---
    elif user_profile.role == "firefighter":
        all_stations = FireStation.objects.all()
        station = user_profile.station

        # 1. Logic Guard: Determine if GPS is missing
        # We check: Station exists -> Address exists -> Lat/Lng are not None
        has_gps = (
            station is not None
            and station.address is not None
            and station.address.latitude is not None
            and station.address.longitude is not None
        )

        context["all_stations"] = all_stations
        context["station_name"] = station.name if station else "Unknown Station"
        context["missing_station_gps"] = not has_gps

        if has_gps:
            context["station_lat"] = float(station.address.latitude)
            context["station_lng"] = float(station.address.longitude)
        else:
            # Pass None so the template/JS doesn't try to render a fake location
            context["station_lat"] = None
            context["station_lng"] = None

        # 2. Radius calculation with safety check
        context["station_radius"] = (
            math.sqrt(station.cover_area_sqm / math.pi) / 1000
            if station and station.cover_area_sqm
            else 3.0
        )

    return render(request, "sensors/maps.html", context)


@login_required(login_url="login")
def upload_layout(request):
    if request.method == "POST":
        form = HouseLayoutForm(request.POST, request.FILES)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.user = request.user
            layout.save()
            return redirect("sensors:maps")
    else:
        form = HouseLayoutForm()
    return render(
        request,
        "sensors/upload_layout.html",
        {
            "form": form,
            "existing_layouts": Houselayout.objects.filter(user=request.user),
        },
    )


@login_required
def get_victim_layout(request, user_id):
    if (
        not hasattr(request.user, "userprofile")
        or request.user.userprofile.role != "firefighter"
    ):
        return JsonResponse({"success": False, "error": "Unauthorized"}, status=403)

    # Use user_id (the owner of the house) to get layouts
    layouts = Houselayout.objects.filter(user_id=user_id)
    results = []

    for l in layouts:
        # Fetch sensors associated with this specific layout
        # Note: Ensure your Sensor model has a 'layout' ForeignKey
        sensors_in_layout = Sensor.objects.filter(layout=l)

        sensors_data = []
        for s in sensors_in_layout:
            sensors_data.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "x": s.x_position,  # Changed to 'x' to match JS s.x
                    "y": s.y_position,  # Changed to 'y' to match JS s.y
                    "status": get_sensor_status(s),
                }
            )

        results.append(
            {
                "layout_id": l.id,
                "layout_name": l.name,
                "image_url": l.image.url,
                "sensors": sensors_data,
            }
        )

    return JsonResponse({"success": True, "layouts": results})


@login_required
@require_POST
def delete_layout_ajax(request, layout_id):
    if request.method == "POST":
        try:
            layout = get_object_or_404(Houselayout, id=layout_id, user=request.user)

            layout.delete()
            messages.success(request, "Layout has been successfully deleted.")
            return redirect("sensors:maps")

        except Exception as e:
            print(f"🚨 ERROR DELETING LAYOUT: {e}")

            messages.error(
                request, "Layout not found or you do not have permission to delete it."
            )
            return redirect("sensors:maps")

    return redirect("sensors:maps")


@login_required
@require_POST
def edit_layout_ajax(request):
    layout_id = request.POST.get("layout_id")
    if not layout_id:
        return JsonResponse(
            {"success": False, "error": "Layout ID is required."}, status=400
        )
    try:
        layout = Houselayout.objects.get(id=layout_id, user=request.user)
    except ObjectDoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Layout not found."}, status=404
        )
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "error": "Invalid Layout ID."}, status=400
        )

    if request.POST.get("name"):
        layout.name = request.POST.get("name")
    if "image" in request.FILES:
        layout.image = request.FILES["image"]
    layout.save()
    return JsonResponse({"success": True})


@login_required
@require_POST
def update_station_coordinates(request):
    try:
        data = json.loads(request.body)
        lat = data.get("lat")
        lng = data.get("lng")

        # Basic coordinate validation
        if lat is None or lng is None:
            return JsonResponse(
                {"success": False, "error": "Coordinates are missing."}, status=400
            )

        # Use select_related to optimize the database hit
        user_profile = request.user.userprofile

        # 1. Authorization & Station Check
        if user_profile.role == "firefighter" and user_profile.station:
            station = user_profile.station

            # 2. Address Presence Check (Crucial for stability)
            if not station.address:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "This station has no address record initialized. Please contact admin.",
                    },
                    status=404,
                )

            # 3. Secure Update Logic
            address = station.address
            address.latitude = lat
            address.longitude = lng
            address.save()

            return JsonResponse({"success": True})

        return JsonResponse(
            {"success": False, "error": "Unauthorized or no station assigned."},
            status=403,
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON format."}, status=400
        )
    except Exception as e:
        # Log for developers, return generic error for users
        print(f"Error in update_station_coordinates: {e}")
        return JsonResponse(
            {"success": False, "error": "An internal server error occurred."},
            status=500,
        )


@login_required
def wildfire_map_view(request):
    if (
        not hasattr(request.user, "userprofile")
        or request.user.userprofile.role != "firefighter"
    ):
        return render(
            request, "sensors/layout/unauthorized.html", {"error": "Unauthorized"}
        )

    user_profile = request.user.userprofile

    # Defensive defaults for the template contract
    station_lat = None
    station_lng = None
    missing_station_gps = True

    # Safely unpack station coordinates if assigned
    if user_profile.station and hasattr(user_profile.station, "address"):
        addr = user_profile.station.address
        if addr and addr.latitude is not None and addr.longitude is not None:
            station_lat = float(addr.latitude)
            station_lng = float(addr.longitude)
            missing_station_gps = (
                False  # Coordinate validation passed, suppress setup overlay
            )

    context = {
        "user_profile": user_profile,
        "role": user_profile.role,
        "station_lat": station_lat,
        "station_lng": station_lng,
        "missing_station_gps": missing_station_gps,
        "all_stations": (
            user_profile.station.__class__.objects.select_related("address").all()
            if user_profile.station
            else []
        ),
    }
    return render(request, "sensors/wildfiremaps.html", context)


@login_required
@require_POST
def wildfire_api_view(request):
    """
    2. API FOR MACHINE CODE (POST)
    Returns raw JSON coordinates secretly to the JavaScript engine.
    """
    if (
        not hasattr(request.user, "userprofile")
        or request.user.userprofile.role != "firefighter"
    ):
        return JsonResponse({"success": False, "error": "Unauthorized"}, status=403)

    user_profile = request.user.userprofile
    station = user_profile.station

    if not station:
        return JsonResponse(
            {"success": False, "error": "No station assigned"}, status=400
        )

    if not hasattr(station, "address") or station.address is None:
        return JsonResponse(
            {"success": False, "error": "Station has no address record."}, status=404
        )

    lat = station.address.latitude
    lng = station.address.longitude
    if lat is None or lng is None:
        return JsonResponse(
            {"success": False, "error": "GPS coordinates are missing."}, status=404
        )

    # 2. Query the database for active fires (e.g., last 24 hours)
    try:
        body = json.loads(request.body)
        requested_days = int(body.get("days", 5))
    except (ValueError, json.JSONDecodeError):
        requested_days = 5
    time_threshold = dj_timezone.now() - timedelta(days=requested_days)
    active_fires = SatelliteHotspot.objects.filter(acq_date__gte=time_threshold.date())

    # 3. Format the hotspots for the frontend
    hotspots_data = []
    for fire in active_fires:
        hotspots_data.append(
            {
                "report_id": fire.id,
                "latitude": fire.location.y,  # PostGIS Point.y is latitude
                "longitude": fire.location.x,  # PostGIS Point.x is longitude
                "frp": fire.frp,
                "brightness": fire.brightness,
                "satellite": fire.satellite,
                "status": "Active",
            }
        )

    return JsonResponse(
        {
            "success": True,
            "lat": float(lat),
            "lng": float(lng),
            "active_hotspots": hotspots_data,
        }
    )
