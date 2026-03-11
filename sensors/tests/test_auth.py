from django.test import TestCase
from django.urls import reverse
from .factories import UserFactory

class RegistrationTest(TestCase):
    def setUp(self):
        self.url = reverse('sensors:register')
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
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'Password123!',  
            'password2': 'Password123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        # Use namespaced URL
        response = self.client.post(reverse('sensors:register'), data)
        
        # Debug: if it still fails, see why
        if response.status_code == 200:
            print(response.context['form'].errors)
            
        self.assertRedirects(response, reverse('sensors:login'))

    def test_register_duplicate_username(self):
        UserFactory(username='taken_user')
        data = self.valid_data.copy()
        data['username'] = 'taken_user'
        
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)


class LoginTest(TestCase):
    def setUp(self):
        self.password = 'secret_login_pass'
        # Create user via factory
        self.user = UserFactory()
        # Manually set the password so we know it for login
        self.user.set_password(self.password)
        self.user.save()
        self.url = reverse('sensors:login')

    def test_login_success(self):
        response = self.client.post(self.url, {
            'username': self.user.username,
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertRedirects(response, reverse('sensors:home'))
    
    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'username': self.user.username,
            'password': 'wrong_password'
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)