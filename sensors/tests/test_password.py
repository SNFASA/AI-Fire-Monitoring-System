from urllib import response
from django.test import TestCase, Client
from django.urls import reverse
from .factories import UserFactory
from django.test import override_settings

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
        
        # FIX: Check if form has errors instead of matching exact text
        form = response.context['form']
        self.assertTrue(form.errors) 
        self.assertIn('old_password', form.errors)

    def test_password_mismatch(self):
        data = {
            'old_password': self.old_password,
            'new_password': 'PasswordA123!',
            'confirm_password': 'PasswordB999!'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        
    @override_settings(AUTH_PASSWORD_VALIDATORS=[{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}}])
    def test_password_too_short(self):
        data = {
            'old_password': self.old_password,
            'new_password': '123',
            'confirm_password': '123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        
        form = response.context['form']
        self.assertTrue(form.errors)