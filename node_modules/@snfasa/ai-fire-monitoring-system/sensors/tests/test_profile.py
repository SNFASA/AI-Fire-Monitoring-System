from django.test import TestCase
from django.urls import reverse

from sensors.models import UserProfile

from .factories import AddressFactory, UserFactory, UserProfileFactory


class ProfileTest(TestCase):
    def setUp(self):
        self.password = "pass123"
        # Use UserProfileFactory to ensure the User AND Profile exist correctly
        self.profile = UserProfileFactory()
        self.user = self.profile.user
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)
        self.url = reverse("sensors:profile")

    def test_profile_view_get(self):
        """TC-2-001: GET view with profile creation."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("u_form", response.context)
        self.assertIn("p_form", response.context)
        self.assertIn("a_form", response.context)

    def test_profile_update_success_with_new_address(self):
        """TC-2-002: Update with new address."""
        # Ensure profile starts with no address to trigger that specific 'if' branch
        self.profile.address = None
        self.profile.save()

        # Build data that satisfies ALL three forms (User, Profile, Address)
        data = {
            # UserUpdateForm fields
            "username": self.user.username,
            "first_name": "Updated",
            "last_name": "Name",
            "email": "updated@example.com",
            # ProfileUpdateForm fields
            "phone_number": "01234567890",
            "bio": "New bio info",
            # AddressUpdateForm fields
            "street": "123 Python Lane",
            "city": "Django City",
            "state": "Selangor",
            "postal_code": "50000",
            "latitude": "3.1390",
            "longitude": "101.6869",
        }

        response = self.client.post(self.url, data)

        # If it still fails, this print statement will tell you exactly which field is mad:
        if response.status_code == 200:
            print("USER FORM ERRORS:", response.context["u_form"].errors)
            print("PROFILE FORM ERRORS:", response.context["p_form"].errors)
            print("ADDRESS FORM ERRORS:", response.context["a_form"].errors)

        self.assertRedirects(response, self.url)

        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(self.user.first_name, "Updated")
        self.assertIsNotNone(self.profile.address)
        self.assertEqual(self.profile.address.street, "123 Python Lane")

    def test_profile_update_invalid(self):
        """Covers the else branch when forms are invalid"""
        # Provide an obviously invalid email
        data = {
            "email": "not-an-email",
            "first_name": "Test",
        }
        response = self.client.post(self.url, data)

        # Should stay on page (200) to show errors
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["u_form"].errors)
