import factory
from django.utils import timezone
from factory.django import DjangoModelFactory
from django.contrib.auth.models import User
from sensors.models import (
    UserProfile, Address, FireStation, Sensor, 
    SensorDataLog, Report, ReportImage, Maintenance, Houselayout
)

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)
    username = factory.Faker('user_name')
    email = factory.Faker('email')
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password('password123')
        if create: self.save()

class AddressFactory(DjangoModelFactory):
    class Meta:
        model = Address
    street = factory.Faker('street_address')
    city = factory.Faker('city')
    state = factory.Faker('state')
    postal_code = factory.Faker('postcode')
    country = 'Malaysia'
    latitude = factory.Faker('pyfloat', left_digits=2, right_digits=6, min_value=-90, max_value=90)
    longitude = factory.Faker('pyfloat', left_digits=3, right_digits=6, min_value=-180, max_value=180)

class FireStationFactory(DjangoModelFactory):
    class Meta:
        model = FireStation
    name = factory.Sequence(lambda n: f"Bomba Station {n+1}")
    address = factory.SubFactory(AddressFactory)
    cover_area_sqm = 50000.0
    contact_number = "999"
    email = factory.Faker('email')

class UserProfileFactory(DjangoModelFactory):
    class Meta:
        model = UserProfile
        django_get_or_create = ('user',)
    user = factory.SubFactory(UserFactory)
    role = 'public'
    phone_number = factory.Faker('numerify', text='01########')
    address = factory.SubFactory(AddressFactory)

class HouselayoutFactory(DjangoModelFactory):
    class Meta:
        model = Houselayout
    user = factory.SubFactory(UserFactory)
    image = factory.django.ImageField(color='blue')
    name = "Ground Floor"

class SensorFactory(DjangoModelFactory):
    class Meta:
        model = Sensor
    owner = factory.SubFactory(UserProfileFactory)
    name = factory.Faker('word')
    is_active = True
    latitude = 3.1390
    longitude = 101.6869
    x_position = 50.0
    y_position = 50.0

class SensorDataLogFactory(DjangoModelFactory):
    class Meta:
        model = SensorDataLog
    sensor = factory.SubFactory(SensorFactory)
    methane = 200
    lpg = 200
    co = 20
    air_quality = 30
    flame_val = 4095
    dht22_temp = 25.0
    humidity = 60.0
    status = 'Safe'

class MaintenanceFactory(DjangoModelFactory):
    class Meta:
        model = Maintenance
    sensor = factory.SubFactory(SensorFactory)
    maintenance_type = 'HealthCheck'
    details = "Routine Check"
    status = 'pending'