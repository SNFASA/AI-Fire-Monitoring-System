import json
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Subquery
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from sensors.filters import SensorFilter

# Local Imports
from ..models import Houselayout, Sensor, SensorDataLog
from ..utils import get_sensor_status

logger = logging.getLogger(__name__)


@login_required
def get_live_data(request):
    try:
        user_profile = request.user.userprofile
        if user_profile is None:
            return JsonResponse(
                {"sensors": [], "message": "User profile not found."}, status=200
            )
        # This line can raise UserProfile.DoesNotExist
        # 1. Fetch sensors specifically for this user's profile
        sensors = Sensor.objects.filter(owner=user_profile).order_by("id")

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
        user_profile = getattr(request.user, "userprofile", None)
        if user_profile is None:
            return JsonResponse(
                {"success": False, "error": "User profile not found."}, status=404
            )

        try:
            layout = Houselayout.objects.get(id=layout_id, user=request.user)
        except Houselayout.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Floor layout not found."}, status=404
            )

        # 3. Create Sensor
        new_sensor = Sensor.objects.create(
            name=name.strip(),
            owner=user_profile,
            layout=layout,
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
@require_POST
def update_sensor_position(request):
    """
    Updates the X/Y coordinates of a sensor on the map layout blueprint.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Method not allowed"}, status=405
        )

    try:
        data = json.loads(request.body)

        # This securely isolates the query loop to the logged-in user context
        sensor = Sensor.objects.get(id=data["sensor_id"], owner__user=request.user)

        sensor.x_position = data["x"]
        sensor.y_position = data["y"]
        sensor.save()

        return JsonResponse({"success": True})

    except Sensor.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Access denied: Unauthorized sensor modification.",
            },
            status=403,
        )

    except (KeyError, ValueError) as e:
        # Handle malformed dictionary payload parameters separately
        return JsonResponse(
            {
                "success": False,
                "message": f"Malformed parameters data layout: {str(e)}",
            },
            status=400,
        )


@login_required
def filters_sensor(request):
    latest_log = (
        SensorDataLog.objects.filter(sensor=OuterRef("pk"))
        .order_by("-timestamp")
        .values("status")[:1]
    )

    # Annotate sensors with their latest log status
    qs = Sensor.objects.filter(owner__user=request.user).annotate(
        current_status=Subquery(latest_log)
    )

    sensor_filter = SensorFilter(request.GET, queryset=qs)
    sensors = sensor_filter.qs

    data = []
    for s in sensors:
        # Determine status: if not active -> Offline, else use latest log
        status = "Offline" if not s.is_active else (s.current_status or "Safe")

        data.append(
            {
                "id": s.id,
                "name": s.name,
                "x_position": s.x_position,
                "y_position": s.y_position,
                "status": status,
                "layout_id": s.layout_id,
            }
        )

    return JsonResponse({"success": True, "sensors": data})
