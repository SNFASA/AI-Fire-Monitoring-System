import factory
from factory.django import DjangoModelFactory
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from sensors.models import (
    UserProfile,
    Address,
    FireStation,
    Sensor,
    SensorDataLog,
    Maintenance,
    Houselayout,
    DutyAssignment,
    Report,
    ReportImage,
    MaintenanceImage,
)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user_{n}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Faker("email")

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password("password123")
        if create:
            self.save()


class AddressFactory(DjangoModelFactory):
    class Meta:
        model = Address

    street = factory.Faker("street_address")
    city = factory.Faker("city")
    state = factory.Faker("state")
    # FIX: Faker 'postcode' can be too long. Using 'numerify' for strict length.
    postal_code = factory.Faker("numerify", text="#####")
    country = "Malaysia"
    latitude = factory.Faker(
        "pyfloat", left_digits=1, right_digits=6, min_value=3.0, max_value=3.2
    )
    longitude = factory.Faker(
        "pyfloat", left_digits=3, right_digits=6, min_value=101.5, max_value=101.7
    )


class FireStationFactory(DjangoModelFactory):
    class Meta:
        model = FireStation

    name = factory.Sequence(lambda n: f"Bomba Station {n+1}")
    address = factory.SubFactory(AddressFactory)
    cover_area_sqm = 50000.0
    # FIX: Faker 'phone_number' often includes extensions or dashes exceeding 15 chars.
    contact_number = factory.Faker("numerify", text="03########")
    email = factory.Faker("email")


class UserProfileFactory(DjangoModelFactory):
    class Meta:
        model = UserProfile
        django_get_or_create = ("user",)

    user = factory.SubFactory(UserFactory)
    role = "public"
    # FIX: Ensuring phone number stays under 15 characters.
    phone_number = factory.Faker("numerify", text="01#########")
    address = factory.SubFactory(AddressFactory)
    station = factory.Maybe(
        factory.LazyAttribute(lambda o: o.role == "firefighter"),
        yes_declaration=factory.SubFactory(FireStationFactory),
        no_declaration=None,
    )


class HouselayoutFactory(DjangoModelFactory):
    class Meta:
        model = Houselayout

    user = factory.SubFactory(UserFactory)
    image = factory.django.ImageField(filename="layout.jpg", color="blue")
    name = factory.Faker("word")


class SensorFactory(DjangoModelFactory):
    class Meta:
        model = Sensor

    owner = factory.SubFactory(UserProfileFactory)
    layout = factory.SubFactory(
        HouselayoutFactory, user=factory.SelfAttribute("..owner.user")
    )
    name = factory.Faker("word")
    is_active = True
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
    status = "Safe"
    timestamp = factory.LazyFunction(timezone.now)


class MaintenanceFactory(DjangoModelFactory):
    class Meta:
        model = Maintenance

    sensor = factory.SubFactory(SensorFactory)
    maintenance_type = "HealthCheck"
    details = "Routine Check"
    status = "Pending"
    scheduled_date = factory.LazyFunction(lambda: timezone.now().date())


class MaintenanceImageFactory(DjangoModelFactory):
    class Meta:
        model = MaintenanceImage

    maintenance = factory.SubFactory(MaintenanceFactory)
    image = factory.django.ImageField(color="green")


class ReportFactory(DjangoModelFactory):
    class Meta:
        model = Report

    station = factory.SubFactory(FireStationFactory)
    trigger_sensor = factory.SubFactory(SensorFactory)
    address = factory.SelfAttribute("trigger_sensor.owner.address")
    status = "System Detected"
    description = factory.Faker("sentence")
    trigger_temperature = factory.Faker("pyfloat", min_value=60, max_value=100)
    # FIX: Faker 'randint' is not a valid provider. Use 'random_int'.
    trigger_gas_level = factory.Faker("random_int", min=800, max=2000)
    timestamp = factory.LazyFunction(timezone.now)

    in_charge = factory.Maybe(
        factory.LazyAttribute(lambda o: o.status == "Confirmed"),
        yes_declaration=factory.SubFactory(UserFactory),
        no_declaration=None,
    )


class DutyAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = DutyAssignment

    firefighter = factory.SubFactory(UserProfileFactory, role="firefighter")
    start_time = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=30))
    end_time = factory.LazyFunction(
        lambda: timezone.now() + timedelta(hours=7, minutes=30)
    )
    is_active = True


class ReportImageFactory(DjangoModelFactory):
    class Meta:
        model = ReportImage

    report = factory.SubFactory(ReportFactory)
    image = factory.django.ImageField(filename="evidence.jpg", color="red")


class MaintenanceImageFactory(DjangoModelFactory):
    class Meta:
        model = MaintenanceImage

    maintenance = factory.SubFactory(MaintenanceFactory)
    image = factory.django.ImageField(filename="evidence.jpg", color="green")
