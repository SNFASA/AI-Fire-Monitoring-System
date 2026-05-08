from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from sensors.filters import MaintenanceFilter
from django.core.paginator import Paginator

# Local Imports
from ..models import (
    UserProfile,
    Maintenance,
    MaintenanceImage,
)

from ..forms import MaintenanceForm


def _check_maintenance_access(request, maintenance):
    """Raise PermissionDenied unless the user is a firefighter or the sensor owner."""
    user_role = getattr(getattr(request.user, "userprofile", None), "role", "public")
    is_firefighter = user_role == "firefighter"
    is_sensor_owner = maintenance.sensor.owner.user == request.user
    if not (is_firefighter or is_sensor_owner):
        raise PermissionDenied


# ==========================================
# 6. MAINTENANCE
# ==========================================
@login_required(login_url="login")
def maintenance_view(request):
    user_profile = request.user.userprofile
    user_role = getattr(user_profile, "role", "public")

    if user_role == "public":
        # Public users see maintenance for sensors they own
        maintenances = (
            Maintenance.objects.filter(sensor__owner=user_profile)
            .select_related("sensor", "nearest_fire_station", "in_charge")
            .prefetch_related("images")
            .order_by("-scheduled_date")
        )
    else:
        # FIREFIGHTER LOGIC:
        # Step 1: Get the firefighter's assigned station from their profile
        firefighter_station = getattr(user_profile, "station", None)

        if firefighter_station:
            # Step 2: Filter Maintenance using the 'nearest_fire_station' field
            maintenances = (
                Maintenance.objects.filter(nearest_fire_station=firefighter_station)
                .select_related("sensor", "nearest_fire_station", "in_charge")
                .prefetch_related("images")
                .order_by("-scheduled_date")
            )
        else:
            maintenances = Maintenance.objects.none()
    maintenances_filter = MaintenanceFilter(request.GET, queryset=maintenances)
    paginator = Paginator(maintenances_filter.qs,10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "sensors/maintenance.html",
        {
            "maintenance_items": page_obj, 
            "user_role": user_role, 
            "page_obj": page_obj, 
            "maintenance_filter": maintenances_filter
        },
    )


@login_required(login_url="login")
def maintenance_detail(request, maintenance_id):
    maintenance = get_object_or_404(
        Maintenance.objects.prefetch_related("images", "sensor"),
        id=maintenance_id,
    )
    _check_maintenance_access(request, maintenance)
    return render(
        request, "sensors/maintenance_detail.html", {"maintenance": maintenance}
    )


@login_required(login_url="login")
@require_POST
def upload_maintenance_evidence(request, maintenance_id):
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    _check_maintenance_access(request, maintenance)
    if "picture" in request.FILES:
        MaintenanceImage.objects.create(
            maintenance=maintenance, image=request.FILES["picture"]
        )
        messages.success(request, "Evidence uploaded!")
    return redirect("sensors:maintenance_detail", maintenance_id=maintenance.id)


@login_required(login_url="login")
def create_maintenance(request):
    if request.method == "POST":
        form = MaintenanceForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            m = form.save()
            for img in request.FILES.getlist("images"):
                MaintenanceImage.objects.create(maintenance=m, image=img)
            return redirect("sensors:maintenance")
    else:
        form = MaintenanceForm(user=request.user)

    return render(request, "sensors/maintenance_create.html", {"form": form})


@login_required(login_url="login")
def edit_maintenance(request, maintenance_id):
    task = get_object_or_404(Maintenance, id=maintenance_id)
    _check_maintenance_access(request, task)

    # 2. ROBUST: Explicitly fetch profile to ensure we get the correct role
    try:
        profile = UserProfile.objects.get(user=request.user)
        user_role = profile.role
    except UserProfile.DoesNotExist:
        user_role = "public"

    if (
        user_role == "public"
        and getattr(task.sensor.owner, "user", None) != request.user
    ):
        raise PermissionDenied("You do not have permission to edit this maintenance.")

    if request.method == "POST":
        if user_role == "public":
            form = MaintenanceForm(
                request.POST, request.FILES, instance=task, user=request.user
            )
            if form.is_valid():
                m = form.save()
                handle_images(request, m)
                # handle_images(request, m) # Ensure this helper exists or import it
                return redirect("sensors:maintenance_detail", maintenance_id=m.id)
        else:
            # Firefighter/Technician Logic
            task.status = request.POST.get("status")
            task.actual_date = (
                request.POST.get("actual_date") or None
            )  # Handle empty strings
            task.technician_notes = request.POST.get("technician_notes")
            if not task.in_charge:
                task.in_charge = request.user
            task.save()
            # handle_images(request, task)
            handle_images(request, task)
            return redirect("sensors:maintenance_detail", maintenance_id=task.id)
    else:
        form = MaintenanceForm(instance=task, user=request.user)

    return render(
        request,
        "sensors/maintenance_edit.html",
        {"form": form, "maintenance": task, "user_role": user_role},
    )


def handle_images(request, maintenance_instance):
    for img in request.FILES.getlist("images"):
        MaintenanceImage.objects.create(maintenance=maintenance_instance, image=img)
    if request.POST.getlist("delete_images"):
        MaintenanceImage.objects.filter(
            id__in=request.POST.getlist("delete_images"),
            maintenance=maintenance_instance,
        ).delete()


@login_required(login_url="login")
@require_POST
def delete_maintenance(request, maintenance_id):
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    _check_maintenance_access(request, maintenance)
    maintenance.delete()
    return redirect("sensors:maintenance")

@login_required
def filter_maintenances(request):
    queryset = Maintenance.objects.select_related('sensor').all().order_by('-scheduled_date')
    maintenance_filter = MaintenanceFilter(request.GET, queryset=queryset)
    data = list(maintenance_filter.qs.values(
        'id',
        'sensor__name',
        'maintenance_type', 
        'frequency', 
        'status', 
        'scheduled_date',
        'actual_date',
        
    ))
    return JsonResponse({"success": True, "maintenances": data})