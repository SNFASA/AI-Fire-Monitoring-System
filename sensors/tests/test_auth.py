from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .factories import UserFactory, UserProfileFactory


class RegistrationTest(TestCase):
    def setUp(self):
        self.url = reverse("sensors:register")
        # .build() creates a non-persisted instance for valid data templates
        user_data = UserFactory.build()
        self.valid_data = {
            "username": user_data.username,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "email": user_data.email,
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }

    def test_register_user_success(self):
        # TC-1-001: Create new user with valid data.
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("sensors:login"))
    def test_register_post_invalid(self):
        """Covers the 'Registration failed' branch in register view."""
        # Sending empty data to trigger form.is_valid() = False
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "Registration failed.")
        
    def test_register_duplicate_username(self):
        # TC-1-002: Duplicate username fails.
        UserFactory(username="taken_user")
        data = self.valid_data.copy()
        data["username"] = "taken_user"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)

    def test_register_passwords_dont_match(self):
        # TC-1-003: Non-matching passwords fail.
        data = self.valid_data.copy()
        data["password2"] = "DifferentPass123!"
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        # Django's default mismatch error: "The two password fields didn’t match."
        self.assertIn("didn’t match", str(form.errors).lower())


class LoginTest(TestCase):
    def setUp(self):
        self.password = "secret_login_pass"
        # Use UserProfileFactory to ensure signals/profiles exist
        self.profile = UserProfileFactory(role="public")
        self.user = self.profile.user
        self.user.set_password(self.password)
        self.user.save()
        self.url = reverse("sensors:login")

    def test_login_success(self):
        "TC-01-004a: Successful login with valid credentials should redirect to home."
        response = self.client.post(
            self.url, {"username": self.user.username, "password": self.password}
        )
        self.assertEqual(response.status_code, 302)
        # Check that the user role (public) redirects to home
        self.assertRedirects(response, reverse("sensors:home"))

    def test_login_firefighter_redirect(self):
        """TC-01-004b: Login as firefighter should redirect to firefighter home."""
        self.profile.role = "firefighter"
        self.profile.save()

        response = self.client.post(
            self.url, {"username": self.user.username, "password": self.password}
        )
        # Expecting firefighter landing page
        self.assertRedirects(response, reverse("sensors:home"))


class AuthExtraTest(TestCase):
    def setUp(self):
        self.password = "old_pass123"
        self.profile = UserProfileFactory()
        self.user = self.profile.user
        self.user.set_password(self.password)
        self.user.save()
        self.client.login(username=self.user.username, password=self.password)

    def test_logout_post(self):
        response = self.client.post(reverse("sensors:logout"))
        self.assertRedirects(response, reverse("sensors:login"))

    def test_change_password_success(self):
        "TC-01-005: Change password should redirect to login."
        data = {
            "old_password": self.password,
            "new_password": "new_pass_456",
            "confirm_password": "new_pass_456",
        }
        response = self.client.post(reverse("sensors:change_password"), data)
        self.assertRedirects(response, reverse("sensors:login"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new_pass_456"))

    def test_change_password_wrong_old(self):

        data = {
            "old_password": "wrong_old_pass",
            "new_password": "new_pass_456",
            "confirm_password": "new_pass_456",
        }
        response = self.client.post(reverse("sensors:change_password"), data)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "Incorrect current password.")
    def test_logout_get_redirect(self):
        """Covers the GET request branch in logout_view (should redirect to home)."""
        response = self.client.get(reverse("sensors:logout"))
        self.assertRedirects(response, reverse("sensors:home"))

    def test_change_password_mismatch(self):
        """Covers the new_password != confirm_password branch."""
        data = {
            "old_password": self.password,
            "new_password": "new_pass",
            "confirm_password": "different_pass",
        }
        response = self.client.post(reverse("sensors:change_password"), data)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(str(messages[0]), "Passwords do not match.")
        
class ProfileViewTest(TestCase):
    def setUp(self):
        self.profile = UserProfileFactory(address=None) # Start without an address
        self.client.force_login(self.profile.user)
        self.url = reverse("sensors:profile")

    def test_profile_get(self):
        """Covers the GET request for profile."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_profile_update_success(self):
        """Covers the POST request: Saving three forms at once + address creation."""
        data = {
            "username": self.profile.user.username, # Required by User form
            "email": self.profile.user.email,       # Required by User form
            "first_name": "Nabil",
            "last_name": "Afifi",
            "phone_number": "0123456789",           # Required by Profile form
            "street": "Jalan UTHM",
            "city": "Parit Raja",
            "state": "Johor",
            "postal_code": "86400",
        }
        response = self.client.post(self.url, data)
        
        # If this fails, it means one of your forms is STILL invalid.
        # To debug in the future, you can print: print(response.context['u_form'].errors)
        self.assertRedirects(response, self.url)
        
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.address)
        self.assertEqual(self.profile.address.street, "Jalan UTHM")

    def test_profile_update_invalid(self):
        """Covers the invalid form branch."""
        # Sending invalid data (e.g., missing required fields)
        response = self.client.post(self.url, {"first_name": ""})
        self.assertEqual(response.status_code, 200)
        # Form should be re-rendered with errors
        self.assertIn("u_form", response.context)
    
    def test_register_get(self):
        """Covers the GET request branch and 'form = SignUpForm()'."""
        # Explicitly use the register URL so it works regardless of which class it is in!
        url = reverse("sensors:register")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertTemplateUsed(response, "sensors/auth/register.html")
    
    def test_change_password_get(self):
        """Covers the GET request branch in change_password."""
        response = self.client.get(reverse("sensors:change_password"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sensors/change_password.html")
    
    def test_profile_update_existing_address(self):
        """Covers the branch where the user ALREADY has an address."""
        # 1. Give the user an address before the POST request
        from .factories import AddressFactory
        existing_address = AddressFactory(street="Old Street")
        self.profile.address = existing_address
        self.profile.save()

        # 2. Submit the form to update it
        data = {
            "username": self.profile.user.username, 
            "email": self.profile.user.email,       
            "first_name": "Nabil",
            "last_name": "Afifi",
            "phone_number": "0123456789",           
            "street": "New Street",  # Updating the street
            "city": "Parit Raja",
            "state": "Johor",
            "postal_code": "86400",
        }
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        
        # 3. Verify it updated the existing address instead of creating a new one
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.address.id, existing_address.id)
        self.assertEqual(self.profile.address.street, "New Street")