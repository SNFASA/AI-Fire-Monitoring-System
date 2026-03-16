from django.shortcuts import render, redirect
from django.db.models import OuterRef, Subquery, Prefetch
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Only import what the dashboard needs to show stats
from ..models import (
    Sensor,
    Maintenance,
    Report,
    FireStation,
    UserProfile,
    SensorDataLog,
)
from .api import predictor

# Initialize AI Engine


@login_required(login_url="login")
def dashboard_view(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile.objects.create(user=request.user)

    sensors = (
        Sensor.objects.filter(owner=user_profile)
        if user_profile.role == "public"
        else Sensor.objects.all()
    )

    context = {
        "sensors_count": sensors.count(),
        "sensors": sensors,
        "ml_model_name": predictor.get_active_model_info(),
        "maintenance_pending": Maintenance.objects.filter(status="Pending").count(),
        "maintenance_items": Maintenance.objects.all().order_by("-timestamp"),
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

    # 2. Portable "Latest Log" Fetch
    # Instead of PostgreSQL-specific .distinct(), we use a Subquery.
    # We find the latest log ID for each specific sensor.
    latest_log_id = (
        SensorDataLog.objects.filter(sensor=OuterRef("sensor"))
        .order_by("-timestamp")
        .values("id")[:1]
    )

    # Filter the logs to only those whose ID matches the latest for that sensor
    latest_readings = SensorDataLog.objects.filter(id__in=Subquery(latest_log_id))

    # 3. Prefetch the readings into the dynamic queryset
    sensors = sensor_qs.prefetch_related(
        Prefetch("readings", queryset=latest_readings, to_attr="latest_log_list")
    ).order_by("id")

    data = []
    for s in sensors:
        # Access the prefetched attribute
        log = s.latest_log_list[0] if s.latest_log_list else None

        data.append(
            {
                "id": s.id,
                "name": s.name,
                "temp": (
                    f"{log.dht22_temp:.1f}"
                    if log and log.dht22_temp is not None
                    else "N/A"
                ),
                "hum": (
                    f"{log.humidity:.1f}" if log and log.humidity is not None else "N/A"
                ),
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
