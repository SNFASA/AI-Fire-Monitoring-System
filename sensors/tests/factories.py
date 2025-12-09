import factory 
from django.contrib.auth.models import User 
from sensors.models import UserProfile 

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
            