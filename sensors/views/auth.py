from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import logout
from ..models import (
    UserProfile,
)
from ..forms import (
    SignUpForm,
    UserUpdateForm,
    ProfileUpdateForm,
    AddressUpdateForm,
)


# ==========================================
# 5. AUTHENTICATION && PROFILE
# ==========================================
def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "Logged out successfully!")
        return redirect("sensors:login")
    return redirect("sensors:home")


def register(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = form.cleaned_data.get("first_name")
            user.last_name = form.cleaned_data.get("last_name")
            user.email = form.cleaned_data.get("email")
            user.save()
            messages.success(request, f"Account created for {user.username}!")
            return redirect("sensors:login")
        else:
            messages.error(request, "Registration failed.")
    else:
        form = SignUpForm()
    return render(request, "sensors/auth/register.html", {"form": form})


@login_required(login_url="login")
def change_password(request):
    if request.method == "POST":
        old_password = request.POST.get("old_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")
        if not request.user.check_password(old_password):
            messages.error(request, "Incorrect current password.")
        elif new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
        else:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, "Password changed!")
            return redirect("sensors:login")
    return render(request, "sensors/change_password.html")


@login_required(login_url="login")
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    current_address = user_profile.address
    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        a_form = AddressUpdateForm(request.POST, instance=user_profile.address)
        if u_form.is_valid() and p_form.is_valid() and a_form.is_valid():
            u_form.save()
            p_form.save()
            address_instance = a_form.save()
            if not user_profile.address:
                user_profile.address = address_instance
                user_profile.save()
            messages.success(request, "Profile updated!")
            return redirect("sensors:profile")
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=user_profile)
        a_form = AddressUpdateForm(instance=current_address)
    context = {
        "u_form": u_form,
        "p_form": p_form,
        "a_form": a_form,
        "user_profile": user_profile,
    }
    messages.success(request, "Profile updated successfully!")
    return render(request, "sensors/profile.html", context)
