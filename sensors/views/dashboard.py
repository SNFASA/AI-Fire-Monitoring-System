from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Only import what the dashboard needs to show stats
from ..models import Sensor, Maintenance, Report, FireStation, UserProfile
from ..logger import get_logs, add_log
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
    user = request.user.userprofile
    sensors = (
        Sensor.objects.filter(owner=user)
        if user.role == "public"
        else Sensor.objects.all()
    )
    data = []
    for s in sensors:
        log = s.readings.last()
        data.append(
            {
                "id": s.id,
                "temp": f"{log.dht22_temp:.1f}" if log else "N/A",
                "hum": f"{log.humidity:.1f}" if log else "N/A",
                "status": log.status if log else "N/A",
            }
        )
    return JsonResponse({"sensors": data})


@login_required
def delete_sensor(request, sensor_id):  # Fallback non-ajax delete
    if request.method == "POST":
        Sensor.objects.get(id=sensor_id, owner__user=request.user).delete()
        return redirect("sensors:dashboard")
    return redirect("sensors:dashboard")


@login_required
@require_POST
def delete_sensor_ajax(request, sensor_id):
    Sensor.objects.get(id=sensor_id, owner__user=request.user).delete()
    return JsonResponse({"success": True, "message": "Deleted"})
