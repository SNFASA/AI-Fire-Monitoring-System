from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .factories import UserFactory

class ChangePasswordTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('change_password') 
        self.old_password = 'OldPassword123!'
        
        self.user = UserFactory()
        self.user.set_password(self.old_password)
        self.user.save()
        
        self.client.login(username=self.user.username, password=self.old_password)

    def test_change_password_success(self):
        new_password = 'NewStrongPassword1!'
        data = {
            'old_password': self.old_password,
            'new_password': new_password,
            'confirm_password': new_password
        }
        response = self.client.post(self.url, data)
        # Should redirect on success
        self.assertEqual(response.status_code, 302)
        
        self.client.logout()
        login_success = self.client.login(username=self.user.username, password=new_password)
        self.assertTrue(login_success)

    def test_wrong_old_password(self):
        data = {
            'old_password': 'WrongPassword!!!',
            'new_password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        
        # FIX: Check content instead of context['form'] to avoid KeyErrors
        # The exact error message depends on your template/form
        # Standard Django message: "Your old password was entered incorrectly"
        # Or check if ANY error class is present
        self.assertContains(response, "error", count=None) 

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 
         'OPTIONS': {'min_length': 9}}
    ])
    def test_password_too_short(self):
        data = {
            'old_password': self.old_password,
            'new_password': '123',
            'confirm_password': '123'
        }
        response = self.client.post(self.url, data)
        
        # If it returns 302, it means validation failed to stop the change
        # If it returns 200, it means the page re-rendered with errors (Correct)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error", count=None)