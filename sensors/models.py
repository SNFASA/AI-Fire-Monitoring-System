from django.db import models
from django.contrib.auth.models import User

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
    
    # Firefighter Specific
    station = models.ForeignKey(FireStation, on_delete=models.SET_NULL, null=True, blank=True)
    position = models.CharField(max_length=100, null=True, blank=True)
    on_duty = models.BooleanField(default=False)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.role}"

# ==========================================
# 3. SENSORS
# ==========================================

class Sensor(models.Model):
    owner = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='sensors')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
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
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

class Report(models.Model):
    station = models.ForeignKey(FireStation, on_delete=models.CASCADE)
    fire_type = models.CharField(max_length=100) 
    cause = models.CharField(max_length=100)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    in_charge = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, limit_choices_to={'userprofile__role': 'firefighter'})
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)