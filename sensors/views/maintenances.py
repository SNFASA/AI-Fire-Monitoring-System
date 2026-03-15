from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
# Local Imports
from ..models import (
    UserProfile,
    Maintenance,
    MaintenanceImage,
)

from ..forms import MaintenanceForm


# ==========================================
# 6. MAINTENANCE
# ==========================================
@login_required(login_url="login")
def maintenance_view(request):
    user_role = getattr(request.user.userprofile, "role", "public")
    if user_role == "public":
        maintenances = Maintenance.objects.filter(
            sensor__owner=request.user.userprofile
        ).order_by("-scheduled_date")
    else:
        maintenances = Maintenance.objects.all().order_by("-scheduled_date")
    return render(
        request,
        "sensors/maintenance.html",
        {"maintenance_items": maintenances, "user_role": user_role},
    )


@login_required(login_url="login")
def maintenance_detail(request, maintenance_id):
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    if request.method == "POST" and "picture" in request.FILES:
        MaintenanceImage.objects.create(
            maintenance=maintenance, image=request.FILES["picture"]
        )
        messages.success(request, "Evidence uploaded!")
        return redirect("sensors:maintenance_detail", maintenance_id=maintenance.id)
    return render(
        request, "sensors/maintenance_detail.html", {"maintenance": maintenance}
    )


@login_required(login_url="login")
def create_maintenance(request):
    if request.method == "POST":
        form = MaintenanceForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save()
            for img in request.FILES.getlist("images"):
                MaintenanceImage.objects.create(maintenance=m, image=img)
            return redirect("sensors:maintenance")
    else:
        form = MaintenanceForm()
    return render(request, "sensors/maintenance_create.html", {"form": form})


@login_required(login_url="login")
def edit_maintenance(request, maintenance_id):
    task = get_object_or_404(Maintenance, id=maintenance_id)

    # 2. ROBUST: Explicitly fetch profile to ensure we get the correct role
    try:
        profile = UserProfile.objects.get(user=request.user)
        user_role = profile.role
    except UserProfile.DoesNotExist:
        user_role = "public"

    if request.method == "POST":
        if user_role == "public":
            form = MaintenanceForm(request.POST, request.FILES, instance=task)
            if form.is_valid():
                m = form.save()
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
            return redirect("sensors:maintenance_detail", maintenance_id=task.id)
    else:
        form = MaintenanceForm(instance=task)

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
def delete_maintenance(request, maintenance_id):
    get_object_or_404(Maintenance, id=maintenance_id).delete()
    return redirect("sensors:maintenance")
