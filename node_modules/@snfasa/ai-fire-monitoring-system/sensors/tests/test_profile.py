from django.test import TestCase, Client
from django.urls import reverse
from sensors.models import UserProfile
from .factories import UserProfileFactory, AddressFactory


class UserProfileViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("sensors:profile")

        # Create user with profile automatically
        self.profile = UserProfileFactory()
        self.user = self.profile.user

        # Ensure address exists
        if not self.profile.address:
            self.profile.address = AddressFactory()
            self.profile.save()

        self.client.login(username=self.user.username, password="password123")

        # Create dummy data for update
        fake_address = AddressFactory.build()
        self.valid_data = {
            "username": self.user.username,
            "first_name": "NewFirst",
            "last_name": "NewLast",
            "email": "new@email.com",
            "phone_number": "0123456789",
            "street": fake_address.street,
            "city": fake_address.city,
            "state": fake_address.state,
            "postal_code": fake_address.postal_code,
        }

    def test_profile_update_success(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "NewFirst")

        updated_profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(updated_profile.address.city, self.valid_data["city"])

    def test_profile_view_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/profile.html")
