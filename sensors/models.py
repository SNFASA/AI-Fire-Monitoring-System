from django.db import models
from django.contrib.auth.models import User
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
    ROLES = (('public', 'Public User'), ('firefighter', 'Firefighter'))
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES, default='public')
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
    
    # Firefighter Specific
    station = models.ForeignKey(FireStation, on_delete=models.SET_NULL, null=True, blank=True)
    position = models.CharField(max_length=100, null=True, blank=True)
    on_duty = models.BooleanField(default=False)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.role}"
#==================================
# 3. House Layout 
#==================================
class Houselayout(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to=user_directory_path)
    name = models.CharField(max_length= 100)
    timestamp = models.DateTimeField(auto_now_add= True)
    
    def __str__(self):
        return f"Layout for {self.user.username}: {self.name}" 
# ==========================================
# 4. SENSORS
# ==========================================

class Sensor(models.Model):
    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='sensors')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    layout = models.ForeignKey(Houselayout, on_delete=models.SET_NULL, null=True, blank=True )
    x_position = models.FloatField(null=True, blank=True, help_text="Horizontal % on floor plan")
    y_position = models.FloatField(null=True, blank=True, help_text="Vertical % on floor plan")
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
    STATUS_CHOICES = (('Pending', 'Pending'), ('InProgress', 'In Progress'), ('Completed', 'Completed'), ('damage','Damage'))
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE)
    details = models.TextField()
    in_charge = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'userprofile__role': 'firefighter'})
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    picture = models.ImageField(upload_to='maintenance/', null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Maintenance for {self.sensor.name} - {self.status}"

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


   