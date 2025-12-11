from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .factories import UserFactory

class RegistrationTest(TestCase):
    
    def setUp(self):
        self.url = reverse('register')
        user_data = UserFactory.build() 
        self.valid_data = {
            'username': user_data.username,
            'first_name': user_data.first_name,
            'last_name': user_data.last_name,
            'email': user_data.email,
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }

    def test_register_user_success(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username=self.valid_data['username']).exists())

    def test_register_duplicate_username(self):
        UserFactory(username='taken_user')
        data = self.valid_data.copy()
        data['username'] = 'taken_user'
        
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)


class LoginTest(TestCase):

    def setUp(self):
        self.password = 'secret_login_pass'
        
        # 1. Create the user using the Factory
        self.user = UserFactory()
        
        # 2. 🔴 CRITICAL FIX: Hash the password manually
        # Without this, the password in the DB is plain text and login fails.
        self.user.set_password(self.password)
        self.user.save()
        
        self.url = reverse('login')

    def test_login_success(self):
        response = self.client.post(self.url, {
            'username': self.user.username,
            'password': self.password
        })
        
        # Debug block (Optional, you can keep it just in case)
        if response.status_code == 200:
            print("\n LOGIN FAILED - DEBUG INFO:")
            if 'form' in response.context:
                print(response.context['form'].errors)

        # Check for success redirect (302)
        self.assertEqual(response.status_code, 302)
        
        # Check that the session now has the user ID (meaning they are logged in)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertRedirects(response, reverse('home'))
    
    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'username': self.user.username,
            'password': 'wrong_password'
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)