import pickle
import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'scaler.pkl')

class FirePredictor:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.load_model()
        
    def load_model(self):
        try:
            with open(MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)
            with open(SCALER_PATH, 'rb') as f:
                self.scaler = pickle.load(f)
            print("✅ HDBMS 7-Feature Model Loaded.")
        except FileNotFoundError:
            print("❌ Model not found. Please run training.py first.")
            self.model = None

    def predict(self, methane, lpg, co, air_quality, flame_val, dht22_temp, humidity):
        """
        Inputs: 7 Raw Sensor Values
        Returns: 'Safe', 'Warning', or 'Fire'
        """
        if not self.model or not self.scaler:
            return "Safe"

        # 1. Feature Vector 
        features = np.array([[methane, lpg, co, air_quality, flame_val, dht22_temp, humidity]])
        
        # 2. Scale
        features_scaled = self.scaler.transform(features)

        # 3. Prediction
        try:
            # Get probability of 'Fire' (Class 1)
            fire_prob = self.model.predict_proba(features_scaled)[0][1]
            
            # --- STATUS LOGIC (Binary -> Trinary) ---
            # Flame Sensor Override (Hardware reliability)
            if flame_val < 500 and dht22_temp > 40:
                return "Fire"

            # Model Probabilities
            if fire_prob >= 0.75:
                return "Fire"       # High confidence
            elif 0.40 <= fire_prob < 0.75:
                return "Warning"    # Medium confidence
            else:
                # Heuristic for Gas Leak (Warning)
                if methane > 600 or lpg > 600:
                    return "Warning"
                    
                return "Safe"
                
        except Exception as e:
            print(f"Prediction Error: {e}")
            return "Safe"