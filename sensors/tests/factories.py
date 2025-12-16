import factory
from factory.django import DjangoModelFactory
from django.contrib.auth.models import User
from sensors.models import UserProfile, Address, Sensor, SensorDataLog

# 1. User Factory
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
        # This ensures the password is hashed properly
        password = extracted or "default_password"
        self.set_password(password)
        if create:
            self.save()

# 2. Address Factory
class AddressFactory(DjangoModelFactory):
    class Meta:
        model = Address

    latitude = factory.Faker('latitude')
    longitude = factory.Faker('longitude')
    street = factory.Faker('word')  # Short string to prevent database errors

# 3. UserProfile Factory
class UserProfileFactory(DjangoModelFactory):
    class Meta:
        model = UserProfile
        django_get_or_create = ('user',)

    user = factory.SubFactory(UserFactory)
    address = factory.SubFactory(AddressFactory)
    phone_number = factory.Faker('numerify', text='01########') # 10 digits
    role = 'public'

# 4. Sensor Factory
class SensorFactory(DjangoModelFactory):
    class Meta:
        model = Sensor

    owner = factory.SubFactory(UserProfileFactory)
    name = factory.Faker('word', ext_word_list=['Kitchen', 'Living Room', 'Bedroom'])
    x_position = factory.Faker('pyfloat', left_digits=2, right_digits=2, positive=True)
    y_position = factory.Faker('pyfloat', left_digits=2, right_digits=2, positive=True)
    is_active = True

# 5. Sensor Data Log Factory
class SensorDataLogFactory(DjangoModelFactory):
    class Meta:
        model = SensorDataLog

    sensor = factory.SubFactory(SensorFactory)
    methane = factory.Faker('random_int', min=0, max=1023)
    lpg = factory.Faker('random_int', min=0, max=1023)
    co = factory.Faker('random_int', min=0, max=1023)
    air_quality = factory.Faker('random_int', min=0, max=1023)
    flame_val = factory.Faker('random_int', min=0, max=4095)
    
    # Use right_digits instead of decimals for pyfloat
    dht22_temp = factory.Faker('pyfloat', min_value=15.0, max_value=40.0, right_digits=1)
    humidity = factory.Faker('pyfloat', min_value=30.0, max_value=90.0, right_digits=1)
    
    status = 'Safe'
    timestamp = factory.Faker('date_time')