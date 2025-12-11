from django.test import TestCase, Client
from django.urls import reverse
from sensors.models import UserProfile
from .factories import UserProfileFactory, UserFactory, AddressFactory

class UserProfileViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('profile')
        self.user = UserFactory()
        self.user.set_password('password123') 
        self.user.save()

        is_logged_in = self.client.login(username=self.user.username, password='password123')
        if not is_logged_in:
            print("⚠️ WARNING: Login failed in setUp!")
        fake_profile = UserProfileFactory.build()
        fake_address = AddressFactory.build()
        
        self.valid_data = {
            'username': self.user.username,
            'first_name': fake_profile.user.first_name,
            'last_name': fake_profile.user.last_name,
            'email': fake_profile.user.email,
            'phone_number': fake_profile.phone_number,
            'street': fake_address.street,
            'city': fake_address.city,
            'state': fake_address.state,
            'postal_code': fake_address.postal_code,
        }

    def test_profile_update_success(self):
        """Test that the view accepts valid data and updates the profile"""
        print("\n--- Testing Profile Update ---")
        
        response = self.client.post(self.url, self.valid_data)
        #  DEBUG 
        if response.status_code == 200:
            print("\n❌ TEST FAILED: Form Validation Errors found:")
            # Check all 3 forms for errors
            if 'u_form' in response.context:
                print(f"User Form Errors: {response.context['u_form'].errors}")
            if 'p_form' in response.context:
                print(f"Profile Form Errors: {response.context['p_form'].errors}")
            if 'a_form' in response.context:
                print(f"Address Form Errors: {response.context['a_form'].errors}")
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, self.valid_data['first_name'])

        updated_profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(updated_profile.address.city, self.valid_data['city'])
        
        print("✅ Test Passed: Profile updated successfully.")

    def test_profile_view_loads(self):
        """Test that the profile page loads correctly (GET request)"""
        print("\n--- Testing Profile Page Load ---")
        response = self.client.get(self.url)
        
        # DEBUG
        if response.status_code == 302:
            print(f"❌ FAILED: Redirected to {response.url} (Likely Login Failure)")
            
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'sensors/profile.html')
        print("✅ Test Passed: Profile page loaded.")