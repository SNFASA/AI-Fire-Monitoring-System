from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import os 

#===========================================
# Helper (upload layout houses)
#===========================================
def user_directory_path(instance, filename):
    return f'floor_plans/user_{instance.user.id}/{filename}'
# ==========================================
# 1. ADDRESS & FIRESTATION 
# ==========================================

class Address(models.Model):
    street = models.CharField(max_length=100)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    postal_code = models.CharField(max_length=10)
    country = models.CharField(max_length=50, default='Malaysia')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.street}, {self.city}"

class FireStation(models.Model):
    name = models.CharField(max_length=100)
    address = models.OneToOneField(Address, on_delete=models.CASCADE)
    cover_area_sqm = models.FloatField(help_text="Coverage area in square meters")
    contact_number = models.CharField(max_length=15)
    email = models.EmailField()
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name}"

# ==========================================
# 2. USERS
# ==========================================

class UserProfile(models.Model):
    # --- Choices ---
    ROLES = (
        ('public', 'Public User'), 
        ('firefighter', 'Firefighter')
    )

    # Based on Malaysian Bomba structure
    RANK_CHOICES = (
        ('KB', 'Ketua Balai (Station Chief)'),
        ('PBK', 'Pegawai Bomba Kanan (Senior Officer/Commander)'),
        ('PB', 'Pegawai Bomba (Firefighter/Crew)'),
        ('Pemandu', 'Driver/Pump Operator'),
    )

    # --- Core Fields ---
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES, default='public')
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.ForeignKey('Address', on_delete=models.SET_NULL, null=True, blank=True) # Used string 'Address' to prevent import errors if Address is defined below
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    status = models.CharField(max_length=20, default='Safe', help_text="Current Aggregate House Status")
    
    # --- Firefighter Specific Fields ---
    station = models.ForeignKey('FireStation', on_delete=models.SET_NULL, null=True, blank=True)
    rank = models.CharField(max_length=20, choices=RANK_CHOICES, null=True, blank=True, help_text="Official Rank")
    team = models.CharField(max_length=50, null=True, blank=True, help_text="E.g. Alpha Squad, Truck 1 Crew")
    position = models.CharField(max_length=100, null=True, blank=True, help_text="Specific role on the truck (e.g., Nozzleman)")
    on_duty = models.BooleanField(default=False)
    
    # --- Timestamps ---
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        # Improved string representation to show Rank if they are a firefighter
        if self.role == 'firefighter' and self.rank:
            return f"{self.rank} {self.user.username} ({self.station})"
        return f"{self.user.username} - {self.role}"
#=========================================
# DutyAssignment (The Rostering Table)
#=========================================
class DutyAssignment(models.Model):
    firefighter = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assignments')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True) # To "soft delete" duties if needed
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # Validation: Ensure firefighter isn't already working during this time
        overlapping = DutyAssignment.objects.filter(
            firefighter=self.firefighter,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError("This firefighter is already assigned to a shift during this time.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.firefighter.user.username}: {self.start_time} - {self.end_time}"
#==================================
# 3. House Layout 
#==================================
class Houselayout(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='layouts')
    # Use a helper function for path if you have one, or simple upload_to
    image = models.ImageField(upload_to='layouts/') 
    name = models.CharField(max_length=100) # e.g. "Ground Floor"
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"
# ==========================================
# 4. SENSORS
# ==========================================

class Sensor(models.Model):
    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='sensors')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    layout = models.ForeignKey(Houselayout, on_delete=models.SET_NULL, null=True, blank=True, related_name='sensors')
    x_position = models.FloatField(null=True, blank=True, help_text="Horizontal % on floor plan")
    y_position = models.FloatField(null=True, blank=True, help_text="Vertical % on floor plan")
    last_status = models.CharField(max_length=20, default='Safe')
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'}) - Owner: {self.owner.user.username} - loc: ({self.latitude}, {self.longitude})"

# ==========================================
# 4. SENSOR DETAILS
# ==========================================

class SensorDataLog(models.Model):
    STATUS_CHOICES = (('Safe', 'Safe'), ('Fire', 'Fire'), ('GasLeak', 'GasLeak'))
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="readings")
    
    # Gas & Fire Readings
    methane = models.IntegerField()
    lpg = models.IntegerField()
    co = models.IntegerField()
    air_quality = models.IntegerField()
    flame_val = models.IntegerField()  
    
    # Env Readings
    dht22_temp = models.FloatField()
    humidity = models.FloatField()
    
    # System Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.status} at {self.timestamp}"

# ==========================================
# 5. MAINTENANCE & REPORTS 
# ==========================================

class Maintenance(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'pending'),
        ('In Progress', 'in_progress'),
        ('Completed','completed'),
        ('Rejected', 'rejected'),
        ('Completed with damages', 'completed_with_damages'),
    )
    TYPE_CHOICES = (
        ('HealthCheck', 'Sensor Health Check'),
        ('Connectivity', 'Connectivity Issue'),
        ('AlarmTest', 'Alarm Test'),
        ('FullAudit', 'Full System Audit'),
        ('Repair', 'Repair/Damage Fix'),
    )
    FRECUENCY_CHOICES = (
        ('adHoc', 'Ad-Hoc/Emergency'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    )
    sensor = models.ForeignKey('Sensor', on_delete=models.CASCADE)
    maintenance_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='HealthCheck')
    frequency = models.CharField(max_length=20, choices=FRECUENCY_CHOICES, default='monthly')
    details = models.TextField(help_text="Describe the issue or reason for maintenance.")
    nearest_fire_station = models.ForeignKey('FireStation', on_delete=models.SET_NULL, null=True, blank=True)
    in_charge = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'userprofile__role': 'firefighter'})
    timestamp = models.DateTimeField(auto_now_add =True)
    scheduled_date = models.DateField(null=True, blank=True) # When the maintenance is planned
    actual_date = models.DateField(null=True, blank=True) # When the maintenance was actually done
    technician_notes = models.TextField(null=True, blank=True, help_text="Notes from the technician after maintenance.")
    updated = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    class Meta:
        ordering = ['-timestamp']
    def __str__(self):
        return f"Maintenance #{self.id} - {self.maintenance_type} for Sensor: {self.sensor.name} - Status: {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.frequency:
            if self.maintenance_type == 'HealthCheck' or self.maintenance_type == 'Connectivity':
                self.frequency = 'monthly'
            elif self.maintenance_type == 'AlarmTest':
                self.frequency = 'quarterly'
            elif self.maintenance_type == 'FullAudit':
                self.frequency = 'yearly'
            else:
                self.frequency = 'adHoc'
        super().save(*args, **kwargs)
#==========================================
# Report model
#+=========================================
class Report(models.Model):
    STATUS_CHOICES = (
        ('System Detected', 'System Detected'),
        ('Confirmed', 'Confirmed Real Fire'),
        ('False Alarm', 'False Alarm'),
        ('Resolved', 'Resolved')
    )

    # -- System Auto-Filled Info --
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='System Detected')
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    # Snapshot of data when fire was detected
    address = models.ForeignKey('Address', on_delete=models.SET_NULL, null=True)
    trigger_sensor = models.ForeignKey('Sensor', on_delete=models.SET_NULL, null=True, help_text="The sensor that first detected the fire")
    trigger_temperature = models.FloatField(null=True, blank=True)
    trigger_gas_level = models.IntegerField(null=True, blank=True, help_text="Combined Gas/Smoke level")
    
    # -- Firefighter Inputs (Nullable because system creates report first) --
    station = models.ForeignKey('FireStation', on_delete=models.SET_NULL, null=True, blank=True)
    in_charge = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'userprofile__role': 'firefighter'})
    fire_type = models.CharField(max_length=100, null=True, blank=True) 
    cause = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True, help_text="Firefighter's detailed report")

    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Report #{self.id} - {self.status} at {self.address}"

# New Model for Multiple Images
class ReportImage(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='reports/evidence/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for Report #{self.report.id}"

class MaintenanceImage(models.Model):
    maintenance = models.ForeignKey(Maintenance, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='maintenance/images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Image for Maintenance #{self.maintenance.id}"
   