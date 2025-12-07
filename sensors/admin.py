from django.contrib import admin
from .models import Address, FireStation, UserProfile, Sensor, SensorDataLog, Maintenance, Report
# Register your models here.

 #==========================================
 # ADMIN REGISTRATION
 #=========================================
 
class AddressAdmin(admin.ModelAdmin):
    list_display = ('street', 'city', 'state', 'postal_code', 'longitude')
    search_fields = ('street', 'city', 'state', 'postal_code')    
    
#==========================================
# FireStation Admin
#=========================================

class FireStationAdmin(admin.ModelAdmin):
    list_display = ('name','contact_number', 'get_city')
    def get_city(self, obj):
        return obj.address.city
    get_city.short_description = 'City'

#==========================================
# UserProfile Admin
#=========================================

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone_number', 'station', 'on_duty')
    list_filter = ('role', 'on_duty', 'station')
    search_fields = ('user__username', 'phone_number')
    
#==========================================
# Sensor Admin
#=========================================

class SensorAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_active', 'latitude', 'longitude')
    list_filter = ('is_active','updated')
    search_fields = ('name', 'owner__user__username')
    
    def location_coords(self, obj):
        return f"({obj.latitude}, {obj.longitude})"
    location_coords.short_description = 'Location'
    
#==========================================
# SENSOR DATA LOG Admin
#=========================================

class SensorDataLogAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'methane', 'lpg', 'co', 'air_quality', 'flame_val', 'dht22_temp', 'humidity', 'status', 'timestamp')
    list_filter = ('status', 'timestamp', 'sensor')
    
    def get_status_color(self, obj):
        if obj.status == 'fire':
            return 'red'
        elif obj.status == 'GasLeak':
            return 'orange'
        return 'green'
    
#==========================================
# MAINTENANCE Admin
#=========================================

class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'status', 'in_charge', 'timestamp')
    list_filter = ('status',)

#==========================================
# REPORT Admin
#=========================================

class ReportAdmin(admin.ModelAdmin):
    list_display = ('station', 'fire_type', 'cause', 'address', 'in_charge', 'timestamp')
    list_filter = ('fire_type', 'station')
    search_fields = ('cause', 'in_charge__username')


#==========================================
# Registering all Admins
#=========================================
admin.site.register(Address, AddressAdmin)
admin.site.register(FireStation, FireStationAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(Sensor, SensorAdmin)
admin.site.register(SensorDataLog, SensorDataLogAdmin)
admin.site.register(Maintenance, MaintenanceAdmin)
admin.site.register(Report, ReportAdmin)

