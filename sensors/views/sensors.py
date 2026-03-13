import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

# Local Imports
from ..models import (
    Sensor,
    Houselayout,
)

from ..utils import get_sensor_status


@login_required
def get_live_data(request):
    try:
        sensors = Sensor.objects.filter(owner=request.user.userprofile).order_by("id")
    except:
        return JsonResponse({"sensors": []})
    data = [
        {
            "id": s.id,
            "name": s.name,
            "status": get_sensor_status(s),
            "x": s.x_position,
            "y": s.y_position,
        }
        for s in sensors
    ]
    return JsonResponse({"sensors": data})


@csrf_exempt
@login_required
def add_sensor(request):
    if request.method == "POST":
        data = json.loads(request.body)
        layout = Houselayout.objects.get(id=data.get("layout_id"), user=request.user)
        new_sensor = Sensor.objects.create(
            owner=request.user.userprofile, name=data.get("name"), layout=layout
        )
        return JsonResponse({"success": True, "sensor_id": new_sensor.id})
    return JsonResponse({"success": False})


@csrf_exempt
@login_required
def update_sensor_position(request):
    """
    Updates the X/Y coordinates of a sensor on the map.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            # 1. MOVED: The get() query MUST be inside the try block
            sensor = Sensor.objects.get(id=data["sensor_id"], owner__user=request.user)

            sensor.x_position = data["x"]
            sensor.y_position = data["y"]
            sensor.save()

            return JsonResponse({"success": True})

        except (Sensor.DoesNotExist, KeyError, ValueError):
            # Returns JSON failure instead of crashing (500)
            return JsonResponse(
                {"success": False, "message": "Sensor not found or access denied"}
            )

    return JsonResponse({"success": False}, status=400)
