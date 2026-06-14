from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.utils.html import format_html

from .models import (
    Address,
    DutyAssignment,
    FireStation,
    Maintenance,
    MaintenanceImage,
    Report,
    Sensor,
    SensorDataLog,
    UserProfile,
    CountryBoundary,
    SatelliteHotspot,
)

# Register your models here.

# ==========================================
# ADMIN REGISTRATION
# =========================================


class AddressAdmin(admin.ModelAdmin):
    list_display = ("street", "city", "state", "postal_code", "longitude")
    search_fields = ("street", "city", "state", "postal_code")


# ==========================================
# FireStation Admin
# =========================================


class FireStationAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_number", "get_city")

    def get_city(self, obj):
        return obj.address.city

    get_city.short_description = "City"


# ==========================================
# UserProfile Admin
# =========================================


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_number", "station", "on_duty")
    list_filter = ("role", "on_duty", "station")
    search_fields = ("user__username", "phone_number")


# ==========================================
# Sensor Admin
# =========================================


class SensorAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_active", "latitude", "longitude")
    list_filter = ("is_active", "updated")
    search_fields = ("name", "owner__user__username")

    def location_coords(self, obj):
        return f"({obj.latitude}, {obj.longitude})"

    location_coords.short_description = "Location"


# ==========================================
# SENSOR DATA LOG Admin
# =========================================


class SensorDataLogAdmin(admin.ModelAdmin):
    # Update list_display to use 'colored_status' instead of just 'status'
    list_display = (
        "sensor",
        "methane",
        "lpg",
        "co",
        "air_quality",
        "flame_val",
        "dht22_temp",
        "humidity",
        "colored_status",
        "timestamp",
    )
    list_filter = ("status", "timestamp", "sensor")

    # Helper function to decide the color (Logic you provided)
    def get_status_color(self, obj):
        if obj.status == "Fire":
            return "red"
        elif obj.status == "Warning":
            return "orange"
        return "green"

    # The function that actually displays the colored HTML
    @admin.display(description="Status")  # Sets the column header name
    def colored_status(self, obj):
        color = self.get_status_color(obj)

        # FIX FOR YOUR ERROR:
        # We pass the color and status as variables, not just a raw string.
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, obj.status
        )


# ==========================================
# MAINTENANCE Admin
# =========================================
class MaintenanceImageInline(admin.TabularInline):
    model = MaintenanceImage
    extra = 1


class MaintenanceAdmin(admin.ModelAdmin):
    inlines = [MaintenanceImageInline]
    list_display = ("sensor", "status", "timestamp", "in_charge")


# ==========================================
# REPORT Admin
# =========================================


class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "station",
        "fire_type",
        "cause",
        "address",
        "in_charge",
        "timestamp",
    )
    list_filter = ("fire_type", "station")
    search_fields = ("cause", "in_charge__username")


# ==========================================
# Duty Assignment Admin
# =========================================
class DutyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "start_time", "end_time")
    list_filter = ("start_time", "end_time")
    search_fields = ("user_profile__user__username",)

    def user_profile(self, obj):
        return obj.firefighter.user.username

    user_profile.short_description = "Firefighter"

# ==========================================
# Country Boundary Admin
# =========================================
# Use gis_admin.GISModelAdmin to get a map widget for the Polygon
class CountryBoundaryAdmin(gis_admin.GISModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
 
# ==========================================
# Satellite Hotspot Admin
# =========================================
# Use gis_admin.GISModelAdmin to get a map widget for the Point
class SatelliteHotspotAdmin(gis_admin.GISModelAdmin):
    # Display the actual fields from your model!
    list_display = ("satellite", "confidence", "frp", "acq_date", "acq_time", "location_coords")
    list_filter = ("satellite", "confidence", "acq_date")
    
    # Custom function to cleanly display the coordinates in the table
    def location_coords(self, obj):
        if obj.location:
            return f"Lat: {obj.location.y}, Lon: {obj.location.x}"
        return "Unknown"
    
    location_coords.short_description = "Coordinates"

# ==========================================
# Registering all Admins
# =========================================
admin.site.register(Address, AddressAdmin)
admin.site.register(FireStation, FireStationAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Sensor, SensorAdmin)
admin.site.register(SensorDataLog, SensorDataLogAdmin)
admin.site.register(Maintenance, MaintenanceAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(SatelliteHotspot, SatelliteHotspotAdmin)
admin.site.register(CountryBoundary, CountryBoundaryAdmin)
admin.site.register(DutyAssignment, DutyAssignmentAdmin)
