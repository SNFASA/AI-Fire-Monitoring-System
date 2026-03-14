from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

# Local Imports
from ..models import (
    UserProfile,
    Report,
    DutyAssignment,
)


# ==========================================s
# 2. MOBILIZE TEAM (CONFIRMATION)
# ==========================================
@login_required
@login_required
@require_POST  # Only allows POST requests; returns 405 for GET, PUT, etc.
def mobilize_team(request, report_id):
    """
    Called when the 'Mobilize Team' button is clicked.
    Assigns the currently on-duty staff to the report.
    """
    try:
        report = Report.objects.get(id=report_id)
        now = timezone.now()

        # Find currently ON-DUTY staff at this station
        active_duties = DutyAssignment.objects.filter(
            firefighter__station=report.station,
            start_time__lte=now,
            end_time__gte=now,
            is_active=True,
        ).select_related("firefighter") # Optimization: avoids N+1 in the loop

        if not active_duties.exists():
            return JsonResponse({
                "success": False,
                "message": "No firefighters are currently on duty at this station!"
            }, status=400)

        # Add them to the team history
        for duty in active_duties:
            report.mobilized_team.add(duty.firefighter)

        # Update report status
        report.status = "Confirmed"
        report.in_charge = request.user
        report.save()

        return JsonResponse({
            "success": True,
            "message": f"Mobilized {active_duties.count()} firefighters.",
        })

    except Report.DoesNotExist:
        return JsonResponse({"success": False, "error": "Report not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login")
@xframe_options_sameorigin
def duty(request):
    """Shows shifts that are currently active or in the future"""
    user_profile = UserProfile.objects.get(user=request.user)

    my_schedule = DutyAssignment.objects.filter(
        firefighter=user_profile,
        is_active=True,
        end_time__gte=timezone.now(),  # Show shifts that haven't ended yet
    ).order_by("start_time")

    return render(request, "sensors/duty_popup.html", {"my_schedule": my_schedule})
