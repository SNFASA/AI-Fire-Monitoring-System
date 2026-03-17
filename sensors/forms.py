from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ObjectDoesNotExist
from .models import UserProfile, Address, Houselayout, Sensor, Maintenance, Report


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(max_length=254, required=True)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")


class AddressUpdateForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["street", "city", "state", "postal_code"]


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(max_length=254, required=True)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            "phone_number",
            "profile_picture",
            "station",
            "rank",
            "team",
            "position",
        ]

        # Add Bootstrap styling to the inputs
        widgets = {
            "rank": forms.Select(attrs={"class": "form-select"}),
            "station": forms.Select(attrs={"class": "form-select"}),
            "team": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Alpha Squad"}
            ),
            "position": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Nozzleman"}
            ),
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            "profile_picture": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if the user is NOT a firefighter
        # We access the instance (the UserProfile object) being edited
        if self.instance and self.instance.role != "firefighter":
            # List of fields to hide/remove for non-firefighters
            firefighter_fields = ["station", "rank", "team", "position"]

            for field in firefighter_fields:
                if field in self.fields:
                    del self.fields[field]


class SensorPlacementForm(forms.ModelForm):
    class Meta:
        model = Sensor
        fields = ["name", "x_position", "y_position"]
        widgets = {
            "x_position": forms.HiddenInput(),
            "y_position": forms.HiddenInput(),
        }


class HouseLayoutForm(forms.ModelForm):
    class Meta:
        model = Houselayout
        fields = ["name", "image"]


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MaintenanceForm(forms.ModelForm):
    class Meta:
        model = Maintenance
        fields = [
            "sensor",
            "maintenance_type",
            "details",
            "nearest_fire_station",
            "scheduled_date",
        ]
        widgets = {
            "sensor": forms.Select(attrs={"class": "form-select"}),
            "maintenance_type": forms.Select(attrs={"class": "form-select"}),
            "nearest_fire_station": forms.Select(attrs={"class": "form-select"}),
            "details": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Describe the issue...",
                }
            ),
            "scheduled_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        # Pop the user out before calling super()
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # 1. Handle the Sensor Dropdown Queryset
        if "sensor" in self.fields:
            if self.user is not None and self.user.is_authenticated:
                profile = getattr(self.user, "userprofile", None)

                if profile and profile.role == "firefighter":
                    # Firefighters can see ALL active sensors
                    self.fields["sensor"].queryset = Sensor.objects.filter(
                        is_active=True
                    )
                elif profile:
                    # Regular owners only see THEIR active sensors
                    self.fields["sensor"].queryset = Sensor.objects.filter(
                        owner=profile, is_active=True
                    )
                else:
                    self.fields["sensor"].queryset = Sensor.objects.none()
            else:
                self.fields["sensor"].queryset = Sensor.objects.none()

        if "nearest_fire_station" in self.fields:
            self.fields["nearest_fire_station"].empty_label = (
                "Select Nearest Fire Station (Optional)"
            )

    def clean_sensor(self):
        # Always define 'sensor' first to prevent UnboundLocalError
        sensor = self.cleaned_data.get("sensor")

        if sensor is not None and self.user is not None:
            profile = getattr(self.user, "userprofile", None)

            if not profile:
                raise forms.ValidationError("User profile not found.")

            # 2. Check Permissions: Allow if they are the owner OR a firefighter
            is_owner = sensor.owner == profile
            is_firefighter = profile.role == "firefighter"

            if not (is_owner or is_firefighter):
                raise forms.ValidationError(
                    "You do not have permission to file maintenance for this sensor."
                )

        return sensor


class ReportCreateForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["fire_type", "cause", "description", "station", "address"]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fire_type": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Building Fire, Vehicle Fire",
                }
            ),
            "cause": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Electrical, Arson",
                }
            ),
            "station": forms.Select(attrs={"class": "form-select"}),
            "address": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["station"].empty_label = "-- Select Fire Station --"
        self.fields["address"].empty_label = "-- Select Address (Optional) --"
        self.fields["address"].required = False


class ReportUpdateForm(forms.ModelForm):
    # Add a checkbox for commanders
    is_approved = forms.BooleanField(
        required=False,
        label="Official Commander Approval",
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input ms-2", "style": "transform: scale(1.5);"}
        ),
    )

    class Meta:
        model = Report
        fields = [
            "fire_type",
            "cause",
            "description",
            "status",
            "station",
            "address",
            "is_approved",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fire_type": forms.TextInput(attrs={"class": "form-control"}),
            "cause": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "station": forms.Select(attrs={"class": "form-select"}),
            "address": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        # 1. Pop the user out of kwargs before initializing the standard form
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # 2. Security Logic: Check rank
        if self.user and hasattr(self.user, "userprofile"):
            rank = self.user.userprofile.rank

            # If they are NOT a Station Chief (KB) or Commander (PBK)
            if rank not in ["KB", "PBK"]:
                # Remove sensitive fields so lower ranks cannot edit them
                if "status" in self.fields:
                    del self.fields["status"]
                if "is_approved" in self.fields:
                    del self.fields["is_approved"]
