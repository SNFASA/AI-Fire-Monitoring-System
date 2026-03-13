from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

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
def mobilize_team(request, report_id):
    """
    Called when the 'Mobilize Team' button is clicked.
    Assigns the currently on-duty staff to the report.
    """
    if request.method == "POST":
        try:
            report = Report.objects.get(id=report_id)
            now = timezone.now()

            # Find currently ON-DUTY staff at this station
            active_duties = DutyAssignment.objects.filter(
                firefighter__station=report.station,
                start_time__lte=now,
                end_time__gte=now,
                is_active=True,
            )

            # Add them to the team history
            for duty in active_duties:
                report.mobilized_team.add(duty.firefighter)

            report.status = "Confirmed"
            report.in_charge = request.user
            report.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Mobilized {active_duties.count()} firefighters.",
                }
            )

        except Report.DoesNotExist:
            return JsonResponse({"error": "Report not found"}, status=404)


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
