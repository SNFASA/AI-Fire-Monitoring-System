import json, logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

# Local Imports
from ..models import (
    Sensor,
    Houselayout,
    UserProfile,
)

from ..utils import get_sensor_status

logger = logging.getLogger(__name__)


@login_required
def get_live_data(request):
    try:
        # 1. Fetch sensors specifically for this user's profile
        sensors = Sensor.objects.filter(owner=request.user.userprofile).order_by("id")

        # 2. Build the data list
        data = [
            {
                "id": s.id,
                "name": s.name,
                "status": get_sensor_status(s),  # Ensure this function is robust!
                "x": s.x_position,
                "y": s.y_position,
            }
            for s in sensors
        ]
        return JsonResponse({"sensors": data})

    except UserProfile.DoesNotExist:
        # This is a handled case: user is logged in but profile isn't ready
        return JsonResponse(
            {"sensors": [], "message": "Profile not found."}, status=200
        )

    except Exception as e:
        # 3. Log the ACTUAL error to your terminal/logs so you can fix it
        logger.error(f"Unexpected error in get_live_data: {e}", exc_info=True)
        return JsonResponse(
            {"sensors": [], "error": "Internal server error"}, status=500
        )


@login_required
@require_POST  # Replaces the 'if request.method == "POST"' check
def add_sensor(request):
    try:
        data = json.loads(request.body)

        # 1. Validate Input Presence
        name = data.get("name")
        layout_id = data.get("layout_id")

        if not name or not str(name).strip():
            return JsonResponse(
                {"success": False, "error": "Sensor name is required."}, status=400
            )

        if not layout_id:
            return JsonResponse(
                {"success": False, "error": "Layout ID is missing."}, status=400
            )

        # 2. Safe Database Lookup
        # Ensures the layout exists AND belongs to the user
        try:
            layout = Houselayout.objects.get(id=layout_id, user=request.user)
        except Houselayout.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Floor layout not found."}, status=404
            )

        # 3. Create Sensor
        new_sensor = Sensor.objects.create(
            owner=request.user.userprofile, name=name.strip(), layout=layout
        )

        return JsonResponse(
            {
                "success": True,
                "sensor_id": new_sensor.id,
                "message": "Sensor registered successfully.",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON payload."}, status=400
        )
    except Exception as e:
        # Catch-all for unexpected issues (e.g., database connection)
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


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
