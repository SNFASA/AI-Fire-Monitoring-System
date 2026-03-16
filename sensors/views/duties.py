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
@require_POST
def mobilize_team(request, report_id):
    """
    Authorizes and mobilizes the on-duty team for a specific report.
    Only firefighters assigned to the report's station can trigger this.
    """
    try:
        # 1. Fetch report and user profile
        report = Report.objects.get(id=report_id)
        user_profile = request.user.userprofile

        # 2. Strict Authorization Check
        # Rule: User must be a firefighter AND belong to the SAME station as the report
        if user_profile.role != "firefighter" or user_profile.station != report.station:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Unauthorized. You can only mobilize teams for your own station.",
                },
                status=403,
            )

        now = timezone.now()

        # 3. Find currently ON-DUTY staff at this station
        active_duties = DutyAssignment.objects.filter(
            firefighter__station=report.station,
            start_time__lte=now,
            end_time__gte=now,
            is_active=True,
        ).select_related("firefighter")

        if not active_duties.exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": "Mobilization failed: No firefighters are currently on duty at this station!",
                },
                status=400,
            )

        # 4. State Update
        # Using a transaction here would be even better if your DB supports it
        for duty in active_duties:
            report.mobilized_team.add(duty.firefighter)

        report.status = "Confirmed"
        report.in_charge = request.user
        report.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Success: {active_duties.count()} firefighters from {report.station.name} mobilized.",
            }
        )

    except Report.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Report not found."}, status=404
        )
    except Exception as e:
        # Log the error for the dev team
        print(f"Mobilize Error: {e}")
        return JsonResponse(
            {"success": False, "error": "An internal server error occurred."},
            status=500,
        )


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
