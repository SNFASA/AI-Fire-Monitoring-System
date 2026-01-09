import factory
import random
from django.utils import timezone
from factory.django import DjangoModelFactory
from django.contrib.auth.models import User
from sensors.models import UserProfile, Address, FireStation, Sensor, SensorDataLog, Report, ReportImage, Maintenance

# 1. Base Helpers
class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Faker('user_name')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.Faker('email')
    
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password('password123') # Default password for everyone
        if create: self.save()

class AddressFactory(DjangoModelFactory):
    class Meta:
        model = Address

    street = factory.Faker('street_address')
    city = factory.Faker('city')
    state = factory.Faker('state')
    postal_code = factory.Faker('postcode')
    latitude = factory.Faker('latitude')
    longitude = factory.Faker('longitude')

class FireStationFactory(DjangoModelFactory):
    class Meta:
        model = FireStation

    name = factory.Sequence(lambda n: f"Fire Station {n+1}")
    address = factory.SubFactory(AddressFactory)
    cover_area_sqm = 50000.0
    contact_number = "999"
    email = factory.Faker('email')

# 2. Profiles
class UserProfileFactory(DjangoModelFactory):
    class Meta:
        model = UserProfile
        django_get_or_create = ('user',)

    user = factory.SubFactory(UserFactory)
    address = factory.SubFactory(AddressFactory)
    role = 'public'
    phone_number = factory.Faker('numerify', text='01########')

# 3. Sensors
class SensorFactory(DjangoModelFactory):
    class Meta:
        model = Sensor

    owner = factory.SubFactory(UserProfileFactory)
    name = factory.Faker('word', ext_word_list=['Kitchen', 'Master Bedroom', 'Garage', 'Living Room'])
    x_position = factory.Faker('pyfloat', min_value=10, max_value=90)
    y_position = factory.Faker('pyfloat', min_value=10, max_value=90)
    is_active = True

# 4. Logs (The most important part!)
class SensorDataLogFactory(DjangoModelFactory):
    class Meta:
        model = SensorDataLog

    sensor = factory.SubFactory(SensorFactory)
    timestamp = factory.Faker('date_time_this_month', tzinfo=timezone.get_current_timezone())
    
    # Default to Safe values
    methane = factory.Faker('random_int', min=100, max=300)
    lpg = factory.Faker('random_int', min=100, max=300)
    co = factory.Faker('random_int', min=10, max=50)
    air_quality = factory.Faker('random_int', min=10, max=50)
    flame_val = 4095 # Safe
    dht22_temp = factory.Faker('pyfloat', min_value=24, max_value=32, right_digits=1)
    humidity = factory.Faker('pyfloat', min_value=50, max_value=80, right_digits=1)
    status = 'Safe'

# 5. Reports & Images
class ReportFactory(DjangoModelFactory):
    class Meta:
        model = Report

    status = 'System Detected'
    address = factory.SubFactory(AddressFactory)
    trigger_sensor = factory.SubFactory(SensorFactory)
    trigger_temperature = factory.Faker('pyfloat', min_value=60, max_value=120, right_digits=1)
    trigger_gas_level = factory.Faker('random_int', min=800, max=2000)
    timestamp = factory.Faker('date_time_this_month', tzinfo=timezone.get_current_timezone())

class ReportImageFactory(DjangoModelFactory):
    class Meta:
        model = ReportImage

    report = factory.SubFactory(ReportFactory)
    # Generates a tiny valid placeholder image file
    image = factory.django.ImageField(color='red')
    
class MaintenanceFactory(DjangoModelFactory):
    class Meta:
        model = Maintenance

    sensor = factory.SubFactory(SensorFactory)
    maintenance_type = 'Repair'
    details = factory.Faker('sentence') # Generates random text
    status = 'Pending'
    scheduled_date = factory.LazyFunction(timezone.now)