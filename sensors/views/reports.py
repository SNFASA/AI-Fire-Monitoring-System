import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

# Local Imports
from ..models import (
    Report,
    FireStation,
    Address,
    ReportImage,
)
from ..forms import ReportUpdateForm

# ==========================================
# 7. REPORTS
# ==========================================


@login_required(login_url="login")
def reports_view(request):
    return render(
        request,
        "sensors/reports.html",
        {"reports": Report.objects.all().order_by("-timestamp")},
    )


@login_required(login_url="login")
def report_detail(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    user_profile = getattr(request.user, 'userprofile', None)
    is_firefighter = user_profile is not None and user_profile.role == "firefighter"

    if request.method == "POST" and is_firefighter:
        report.fire_type = request.POST.get("fire_type")
        report.cause = request.POST.get("cause")
        report.description = request.POST.get("description")
        report.status = request.POST.get("status")
        station_id = request.POST.get("station")
        if station_id:
            report.station = get_object_or_404(FireStation, id=station_id)

        report.in_charge = request.user
        report.save()

        for img in request.FILES.getlist("images"):
            ReportImage.objects.create(report=report, image=img)

        messages.success(request, "Report updated!")
        return redirect("sensors:reports")

    return render(
        request,
        "sensors/report_detail.html",
        {
            "report": report,
            "stations": FireStation.objects.all(),
            "is_firefighter": is_firefighter,
        },
    )


@login_required(login_url="login")
def create_report(request):
    if request.method == "POST":
        try:
            station = FireStation.objects.get(id=request.POST.get("station"))
            address = (
                Address.objects.get(id=request.POST.get("address"))
                if request.POST.get("address")
                else None
            )
            report = Report.objects.create(
                status="Confirmed",
                fire_type=request.POST.get("fire_type"),
                cause=request.POST.get("cause"),
                description=request.POST.get("description"),
                station=station,
                address=address,
                in_charge=request.user,
            )
            for img in request.FILES.getlist("images"):
                ReportImage.objects.create(report=report, image=img)
            return redirect("sensors:report_detail", report_id=report.id)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "sensors/create_report.html",
        {"stations": FireStation.objects.all(), "addresses": Address.objects.all()},
    )


def check_firefighter_role(user):
    """Ensures only firefighters can edit/delete"""
    if not hasattr(user, "userprofile") or user.userprofile.role != "firefighter":
        raise PermissionDenied("You do not have permission to perform this action.")


@login_required(login_url="login")
def edit_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    # 1. Security Check
    check_firefighter_role(request.user)

    if request.method == "POST":
        # Load form with POST data
        form = ReportUpdateForm(request.POST, instance=report)

        if form.is_valid():
            # Save basic data
            updated_report = form.save(commit=False)
            updated_report.in_charge = request.user
            updated_report.save()

            # Handle Images (Keep your existing logic, it's good)
            handle_report_images(request, updated_report)

            messages.success(request, f"Report #{report.id} updated successfully!")
            return redirect("sensors:report_detail", report_id=report.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Load form with existing data
        form = ReportUpdateForm(instance=report)

    context = {
        "form": form,
        "report": report,
    }
    return render(request, "sensors/update_report.html", context)


@login_required(login_url="login")
@require_POST  # Security: Prevent deletion via simple browser link click (GET)
def delete_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    # 1. Security Check
    check_firefighter_role(request.user)

    # 2. Cleanup: Delete image files associated with this report
    for img_obj in report.images.all():
        if img_obj.image and os.path.isfile(img_obj.image.path):
            os.remove(img_obj.image.path)  # Delete file from disk

    # 3. Delete DB Record
    report_id_ref = report.id
    report.delete()

    messages.success(request, f"Report #{report_id_ref} deleted.")
    return redirect("sensors:reports")


# --- IMAGE HANDLER (Kept mostly same, added file cleanup) ---
def handle_report_images(request, report_instance):
    # 1. Add New Images
    for img in request.FILES.getlist("images"):
        ReportImage.objects.create(report=report_instance, image=img)

    # 2. Delete Selected Images
    delete_ids = request.POST.getlist("delete_images")
    if delete_ids:
        images_to_delete = ReportImage.objects.filter(
            id__in=delete_ids, report=report_instance
        )
        # Delete actual files from disk before deleting DB record
        for img_obj in images_to_delete:
            if img_obj.image and os.path.isfile(img_obj.image.path):
                os.remove(img_obj.image.path)

        images_to_delete.delete()
