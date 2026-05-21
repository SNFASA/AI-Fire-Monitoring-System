from django.test import Client, TestCase
from django.urls import reverse

from .factories import UserFactory


class ChangePasswordTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse("sensors:change_password")
        self.old_password = "OldPassword123!"

        self.user = UserFactory()
        self.user.set_password(self.old_password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.old_password)

    def test_change_password_success(self):
        new_password = "NewStrongPassword1!"
        data = {
            "old_password": self.old_password,
            "new_password": new_password,
            "confirm_password": new_password,
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)

        self.client.logout()
        login_success = self.client.login(
            username=self.user.username, password=new_password
        )
        self.assertTrue(login_success)

    def test_wrong_old_password(self):
        data = {
            "old_password": "WrongPassword!!!",
            "new_password": "NewPassword123!",
            "confirm_password": "NewPassword123!",
        }
        response = self.client.post(self.url, data)

        # Expect 200 (Form re-rendered with errors)
        self.assertEqual(response.status_code, 200)

        # Check that the response content indicates an error
        # This checks for "error" class or text in the HTML
        self.assertContains(response, "error", count=None)

    def test_password_mismatch(self):

        data = {
            "old_password": self.old_password,
            "new_password": "PasswordA123!",
            "confirm_password": "PasswordB999!",
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error", count=None)
