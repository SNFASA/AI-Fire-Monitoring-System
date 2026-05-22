import os
import random 
import joblib
import uuid
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User  
from sensors.models import Sensor, SensorDataLog, UserProfile

from ml_engine.hdbms_controller import run_hdbms_training_task 

class MachineLearningAutomationTests(TestCase):

    def setUp(self):
        unique_suffix = uuid.uuid4().hex[:6]
        self.user = User.objects.create_user(username=f"ml_tester_{unique_suffix}", password="password123")
        
        if hasattr(self.user, 'userprofile'):
            self.user.userprofile.delete()

        self.profile = UserProfile.objects.create(user=self.user, role="public")
        self.sensor = Sensor.objects.create(id=99, name="ML Baseline Unit", owner=self.profile)
        
        statuses = ["Safe", "Warning", "Fire", "Gas Leak"]
        
        # FIX: Increase the loop range to exceed the 100 minimum log threshold
        for i in range(105):  
            SensorDataLog.objects.create(
                sensor=self.sensor,
                methane=300 if i % 2 == 0 else 1500,
                lpg=300 if i % 2 == 0 else 1200,
                co=80 if i % 2 == 0 else 900,
                air_quality=100,
                flame_val=4095 if i % 3 != 0 else 300,
                dht22_temp=28.0 if i % 4 != 0 else 55.0,
                humidity=60.0,
                status=random.choice(statuses),
                timestamp=timezone.now()
            )

    def test_hdbms_compilation_and_file_write(self):
        """Verifies multi-model ensemble ranking processes run and overwrite current pickling assets."""
        model_path = "ml_engine/fire_model.pkl"
        
        # Execute the training pipeline block directly
        run_hdbms_training_task()
        
        # Assert the persistence file asset was safely compiled and placed on local server storage disk
        self.assertTrue(os.path.exists(model_path))
        
        # Load object framework descriptor to verify file structure integrity parameter passes
        loaded_classifier = joblib.load(model_path)
        self.assertTrue(hasattr(loaded_classifier, "predict"))