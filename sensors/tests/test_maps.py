from django.test import TestCase, Client
from django.urls import reverse
# ADD AddressFactory to the imports
from .factories import UserProfileFactory, SensorDataLogFactory, SensorFactory, AddressFactory

class FirefighterMapLoadTest(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Setup Firefighter (Force Role & Password)
        self.firefighter_profile = UserProfileFactory(user__username='chief_fire')
        self.firefighter_profile.role = 'firefighter'
        self.firefighter_profile.save()
        
        user = self.firefighter_profile.user
        user.set_password('password123')
        user.save()

        # 2. Setup Public Users (Victims)
        self.public_users = []
        for i in range(10):
            profile = UserProfileFactory(
                user__username=f'PublicUser{i}',
                role='public',
            )
            
            # --- CRITICAL FIX: MANUALLY ADD ADDRESS ---
            # The signal created the profile without an address. We must add one.
            if not profile.address:
                profile.address = AddressFactory()
                profile.save()
            # ------------------------------------------

            s1 = SensorFactory(owner=profile, name='Kitchen')
            
            # Create 1 Fire (at index 2)
            if i == 2:
                SensorDataLogFactory(
                    sensor=s1, 
                    status='Fire', 
                    methane=1023,
                    lpg=1023,
                    co=1023,
                    air_quality=1023,
                    flame_val=100,
                    dht22_temp=80.0,
                    humidity=80.0
                )
            else:
                SensorDataLogFactory(sensor=s1, status='Safe')
                
            self.public_users.append(profile)
            
    def test_map_api_returns_10_houses(self):
        # 1. Login
        login_success = self.client.login(username='chief_fire', password='password123')
        self.assertTrue(login_success, "Firefighter login failed - check setUp()")

        # 2. Call the API
        response = self.client.get(reverse('sensors:map_data')) 
        
        # 3. Check Status
        self.assertEqual(response.status_code, 200, f"API failed with status {response.status_code}")

        # 4. Check Data
        data = response.json()
        print(f"\nGenerated {len(data.get('houses', []))} houses for testing.")
        
        self.assertEqual(len(data['houses']), 10, "Should return 10 houses")
        
        fire_houses = [h for h in data['houses'] if h['status'] == 'Fire']
        print(f"Houses on Fire: {len(fire_houses)}") 
        
        self.assertEqual(len(fire_houses), 1, "Should have exactly 1 house on fire")