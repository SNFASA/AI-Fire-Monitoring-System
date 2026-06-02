import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from sensors.filters import ReportFilter

from ..forms import ReportCreateForm, ReportUpdateForm

# Local Imports
from ..models import FireStation, Report, ReportImage


# ==========================================
# 7. REPORTS
# ==========================================
@login_required(login_url="login")
def reports_view(request):
    user_profile = request.user.userprofile
    user_role = getattr(user_profile, "role", "public")

    # 1. Base Queryset: Secure the data based on the user's role
    if user_role == "public":
        base_queryset = (
            Report.objects.filter(trigger_sensor__owner=request.user.userprofile)
            .select_related("address", "station", "trigger_sensor")
            .prefetch_related("images", "in_charge")
            .order_by("-timestamp")
        )
    else:
        firefighter_station = getattr(user_profile, "station", None)
        if firefighter_station:
            base_queryset = (
                Report.objects.filter(station=firefighter_station)
                .select_related("address", "station", "trigger_sensor")
                .prefetch_related("images", "in_charge")
                .order_by("-timestamp")
            )
        else:
            base_queryset = Report.objects.none()

    # 2. Apply Filters: Pass the secure base_queryset into your ReportFilter
    report_filter = ReportFilter(request.GET, queryset=base_queryset)

    # 3. Pagination: Apply pagination to the FILTERED results (.qs)
    # We use 10 reports per page, you can change this number
    paginator = Paginator(report_filter.qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # 4. Context: Send the filter, the paginated objects, and the role to the template
    context = {
        "filter": report_filter,
        "reports": page_obj,
        "page_obj": page_obj,
        "user_role": user_role,
    }

    return render(request, "sensors/reports.html", context)


@login_required(login_url="login")
def report_detail(request, report_id):
    qs = Report.objects.select_related(
        "station", "address", "trigger_sensor"
    ).prefetch_related("images")
    report = get_object_or_404(qs, id=report_id)

    user_profile = getattr(request.user, "userprofile", None)
    user_role = getattr(user_profile, "role", "public")

    if user_role == "firefighter":
        firefighter_station = getattr(user_profile, "station", None)
        if report.station != firefighter_station:
            raise PermissionDenied(
                "You can only view reports assigned to your specific fire station."
            )

    elif user_role == "public":
        if report.trigger_sensor and report.trigger_sensor.owner != user_profile:
            raise PermissionDenied("You do not have permission to view this report.")

    is_firefighter = user_role == "firefighter"
    user_rank = getattr(user_profile, "rank", None) if user_profile else None
    is_commander = user_rank in ["KB", "PBK"]

    if request.method == "POST" and is_firefighter:
        report.fire_type = request.POST.get("fire_type", report.fire_type) or ""
        report.cause = request.POST.get("cause", report.cause) or ""
        report.description = request.POST.get("description", report.description) or ""

        station_id = request.POST.get("station")
        if station_id:
            report.station = get_object_or_404(FireStation, id=station_id)

        report.in_charge = request.user

        if is_commander:
            status_val = request.POST.get("status")
            if status_val:
                report.status = status_val

            if request.POST.get("is_approved") == "on":
                report.is_approved = True
                report.approved_by = request.user
            else:
                report.is_approved = False
                report.approved_by = None
        else:
            report.is_approved = False
            report.approved_by = None

        report.save()

        delete_ids = request.POST.getlist("delete_images")
        if delete_ids:
            ReportImage.objects.filter(id__in=delete_ids).delete()

        # Save any uploaded images
        for img in request.FILES.getlist("images"):
            ReportImage.objects.create(report=report, image=img)

        messages.success(request, "Report updated successfully!")
        return redirect("sensors:report_detail", report_id=report.id)

    return render(
        request,
        "sensors/report_detail.html",
        {
            "report": report,
            "stations": FireStation.objects.all(),
            "is_firefighter": is_firefighter,
        },
    )


def check_firefighter_role(user):
    """Ensures only firefighters can edit/delete"""
    if not hasattr(user, "userprofile") or user.userprofile.role != "firefighter":
        raise PermissionDenied("You do not have permission to perform this action.")


@login_required(login_url="login")
def create_report(request):
    # Restrict to firefighters only
    check_firefighter_role(request.user)

    if request.method == "POST":
        form = ReportCreateForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.in_charge = request.user
            # Status defaults to STATUS_SYSTEM_DETECTED via model default
            report.save()
            for img in request.FILES.getlist("images"):
                ReportImage.objects.create(report=report, image=img)
            return redirect("sensors:report_detail", report_id=report.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ReportCreateForm()

    return render(
        request,
        "sensors/create_report.html",
        {"form": form},
    )


@login_required(login_url="login")
def edit_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    # 1. Security Check (Assume this checks if they are a firefighter)
    # check_firefighter_role(request.user)

    user_rank = getattr(request.user.userprofile, "rank", None)
    is_commander = user_rank in ["KB", "PBK"]

    if request.method == "POST":
        # Pass the user into the form
        form = ReportUpdateForm(request.POST, instance=report, user=request.user)

        if form.is_valid():
            updated_report = form.save(commit=False)
            updated_report.in_charge = request.user

            # --- APPROVAL LOGIC ---
            if not is_commander:
                # Lower ranks editing the report resets approval automatically
                updated_report.is_approved = False
                updated_report.approved_by = None
            else:
                # If commander checks the box, record their name
                if updated_report.is_approved and not report.is_approved:
                    updated_report.approved_by = request.user
                # If commander unchecks the box
                elif not updated_report.is_approved:
                    updated_report.approved_by = None

            updated_report.save()

            # Handle Images (Keep your existing logic)
            handle_report_images(request, updated_report)

            messages.success(request, f"Report #{report.id} updated successfully!")
            return redirect("sensors:report_detail", report_id=report.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Load form with existing data, passing the user
        form = ReportUpdateForm(instance=report, user=request.user)

    context = {
        "form": form,
        "report": report,
        "is_commander": is_commander,  # Pass this to HTML to show/hide UI elements
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


@login_required
def filter_reports(request):
    # Base queryset optimized with select_related
    queryset = (
        Report.objects.select_related("station", "address", "trigger_sensor")
        .all()
        .order_by("-timestamp")
    )

    # Apply the filters
    report_filter = ReportFilter(request.GET, queryset=queryset)

    # Extract exactly the data needed for the JsonResponse
    data = list(
        report_filter.qs.values(
            "id",
            "fire_type",
            "cause",
            "description",
            "status",
            "is_approved",
            "timestamp",
            "station__name",
            "address__full_address",  # Ensure Address model has 'full_address' property/field
            "trigger_sensor__name",
        )
    )

    return JsonResponse({"success": True, "reports": data})
