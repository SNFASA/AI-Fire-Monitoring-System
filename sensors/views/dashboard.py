from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Prefetch, Subquery
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

# Only import what the dashboard needs to show stats
from ..models import (
    FireStation,
    Maintenance,
    Report,
    Sensor,
    SensorDataLog,
    UserProfile,
)
from .api import predictor


@login_required(login_url="login")
def dashboard_view(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile.objects.create(user=request.user)

    # 1. Filter Sensors based on role
    if user_profile.role == "public":
        sensors = Sensor.objects.filter(owner=user_profile)
    else:
        sensors = Sensor.objects.all()

    # 2. Filter Maintenance based on role
    if user_profile.role == "public":
        # Get maintenance records only for sensors owned by this public user
        base_maintenance_qs = Maintenance.objects.filter(sensor__in=sensors)
        
    elif user_profile.role == "firefighter":
        # Get maintenance records only for this firefighter's assigned station
        if user_profile.station:
            base_maintenance_qs = Maintenance.objects.filter(nearest_fire_station=user_profile.station)
        else:
            # Safe fallback if a firefighter has no station assigned yet
            base_maintenance_qs = Maintenance.objects.none()
            
    else:
        # Fallback for any other unexpected roles
        base_maintenance_qs = Maintenance.objects.none()

    context = {
        "sensors_count": sensors.count(),
        "sensors": sensors,
        "ml_model_name": predictor.get_active_model_info(),
        
        # FIX: Use __iexact to catch both "Pending" and "pending"
        "maintenance_pending": base_maintenance_qs.filter(status__iexact="pending").count(),
        "maintenance_items": base_maintenance_qs.order_by("-timestamp"),
        
        "reports_count": Report.objects.count(),
        "recent_reports": Report.objects.all().order_by("-timestamp"),
        "stations_count": FireStation.objects.count(),
    }
    
    return render(request, "sensors/dashboard.html", context)


@login_required
def get_dashboard_sensor_data(request):
    user_profile = request.user.userprofile

    # 1. Base Queryset based on Role
    if user_profile.role == "public":
        sensor_qs = Sensor.objects.filter(owner=user_profile)
    else:
        sensor_qs = Sensor.objects.all()

    # 2. The Optimized PostgreSQL Fetch
    # This grabs the absolute latest log for each sensor in milliseconds
    latest_readings = SensorDataLog.objects.order_by("sensor_id", "-timestamp").distinct("sensor_id")

    # 3. Prefetch the readings into the dynamic queryset
    sensors = sensor_qs.prefetch_related(
        Prefetch("readings", queryset=latest_readings, to_attr="latest_log_list")
    ).order_by("id")

    data = []
    for s in sensors:
        log = s.latest_log_list[0] if s.latest_log_list else None

        data.append(
            {
                "id": s.id,
                "name": s.name,
                "temp": f"{log.dht22_temp:.1f}" if log and log.dht22_temp is not None else "N/A",
                "hum": f"{log.humidity:.1f}" if log and log.humidity is not None else "N/A",
                "status": log.status if log else "Offline",
            }
        )

    return JsonResponse({"sensors": data})


@login_required
def delete_sensor(request, sensor_id):
    if request.method == "POST":
        try:
            sensor = Sensor.objects.get(id=sensor_id, owner__user=request.user)
            sensor.delete()
            messages.success(request, "Sensor deleted successfully.")
        except Sensor.DoesNotExist:
            messages.error(request, "Error: Sensor not found or permission denied.")

    return redirect("sensors:dashboard")


@login_required
@require_POST
def delete_sensor_ajax(request, sensor_id):
    try:
        # Ensure the sensor exists AND belongs to the logged-in user
        sensor = Sensor.objects.get(id=sensor_id, owner__user=request.user)
        sensor.delete()
        return JsonResponse(
            {"success": True, "message": "Sensor deleted successfully."}
        )

    except Sensor.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Sensor not found or you do not have permission to delete it.",
            },
            status=404,
        )
