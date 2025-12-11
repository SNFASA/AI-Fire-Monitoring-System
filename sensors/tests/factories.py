import factory 
from django.contrib.auth.models import User 
from sensors.models import UserProfile, Address

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User 
        
    username = factory.Faker('user_name')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.Faker('email')
    
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        password = extracted or "default_password"
        self.set_password(password)
        if create:
            self.save()
# 1. Factory for the User model
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Faker('user_name')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.Faker('email')

# 2. Factory for the Address model
class AddressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Address

    street = factory.Faker('street_address')
    city = factory.Faker('city')
    state = factory.Faker('state')
    postal_code = factory.Faker('postcode')

# 3. Factory for UserProfile
class UserProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserProfile

    user = factory.SubFactory(UserFactory)
    address = factory.SubFactory(AddressFactory)
    phone_number = factory.Faker('phone_number')
    role = 'public'