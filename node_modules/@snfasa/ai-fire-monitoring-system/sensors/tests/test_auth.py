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
