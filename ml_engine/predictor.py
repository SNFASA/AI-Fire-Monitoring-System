import pickle 
import os 
import numpy as np 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')

class FirePredictor:
    def __init__(self):
        self.model = None
        self.load_model()
        # MAPPED LABELS: Ensure consistent naming
        self.labels = {
            0: 'Safe',
            1: 'Fire',
            2: 'Warning' # Renamed from 'Gas Leak' to 'Warning' for system consistency
        }
        
    def load_model(self):
        try:
            with open(MODEL_PATH, 'rb') as f :
                self.model = pickle.load(f)
            print("✅ AI Model Loaded.")
        except FileNotFoundError:
            print("❌ Model missing.")
            self.model = None
            
    def predict(self, methane, lpg, co, air_quality, flame_val, dht22_temp, humidity):
        if self.model is None: return "Safe"
        
        # Safety fallback logic if model is erratic
        # If flame is very close (low value) OR temp is very high -> Force Fire
        if flame_val < 500 or dht22_temp > 60:
            return "Fire"
            
        inputs = [[methane, lpg, co, air_quality, flame_val, dht22_temp, humidity]]
        
        try:
            pred = self.model.predict(inputs)[0]
            return self.labels.get(pred, "Safe")
        except:
            return "Safe"