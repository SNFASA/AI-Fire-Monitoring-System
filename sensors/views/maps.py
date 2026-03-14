import math, json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Local Imports
from ..models import (
    Sensor,
    UserProfile,
    FireStation,
    Houselayout,
)
from ..forms import HouseLayoutForm
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
        # CRITICAL FIX: Ignore if Lat/Lng is None to prevent map crash
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
                if s_status == "Fire":
                    house_status = "Fire"
                    break
                elif s_status == "Gas Leak" and house_status != "Fire":
                    house_status = "Gas Leak"
                elif s_status == "Offline":
                    has_offline = True

            if house_status == "Safe" and has_offline and sensors.exists():
                house_status = "Offline"

            data.append(
                {
                    "id": profile.user.id,
                    "owner": profile.user.username,
                    "lat": profile.address.latitude,
                    "lng": profile.address.longitude,
                    "status": house_status,
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

    if user_profile.role == "public":
        user_layouts = Houselayout.objects.filter(user=request.user).order_by("id")
        selected_layout_id = request.GET.get("layout_id")
        current_layout = (
            user_layouts.filter(id=selected_layout_id).first()
            if selected_layout_id
            else user_layouts.first()
        )

        context["layouts"] = user_layouts
        context["current_layout"] = current_layout
        context["sensors"] = (
            Sensor.objects.filter(owner=user_profile, layout=current_layout)
            if current_layout
            else []
        )

    elif user_profile.role == "firefighter":
        all_stations = FireStation.objects.all()
        station = user_profile.station

        context["all_stations"] = all_stations
        context["station_name"] = station.name if station else "HQ"
        context["station_lat"] = (
            float(station.address.latitude) if station and station.address else 1.8548
        )
        context["station_lng"] = (
            float(station.address.longitude)
            if station and station.address
            else 103.0848
        )
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
    Houselayout.objects.get(id=layout_id, user=request.user).delete()
    return JsonResponse({"success": True, "message": "Deleted"})


@login_required
@require_POST
def edit_layout_ajax(request):
    layout = Houselayout.objects.get(
        id=request.POST.get("layout_id"), user=request.user
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

        user_profile = request.user.userprofile
        if user_profile.role == "firefighter" and user_profile.station:
            address = user_profile.station.address
            address.latitude = lat
            address.longitude = lng
            address.save()
            return JsonResponse({"success": True})

        return JsonResponse(
            {"success": False, "error": "Unauthorized or no station assigned."},
            status=403,
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
