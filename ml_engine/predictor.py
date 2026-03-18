import pickle
import os
import numpy as np
import pandas as pd

# Import logging function to allow predictor to log decisions
from sensors.logger import add_log

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fire_model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")


class FirePredictor:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.load_model()

    def load_model(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            with open(SCALER_PATH, "rb") as f:
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

        # Note: Inputs are logged in views.py now, so we focus on Logic here.

        if not self.model or not self.scaler:
            return "Safe"

        if flame_val <= 0 or dht22_temp == 0:
            add_log("⚠️ WARNING: Sensor Malfunction/Disconnected. Skipping AI.\n")
            return "Safe"

        try:
            # 1. Feature Vector
            cols = [
                "methane",
                "lpg",
                "co",
                "air_quality",
                "flame_val",
                "dht22_temp",
                "humidity",
            ]
            features = pd.DataFrame(
                [[methane, lpg, co, air_quality, flame_val, dht22_temp, humidity]],
                columns=cols,
            )

            # 2. Scale
            features_scaled = self.scaler.transform(features)

            # 3. Get Probability
            # This fixes the "fire_prob is not defined" error
            fire_prob = self.model.predict_proba(features_scaled)[0][1]
            prob_percent = round(fire_prob * 100, 1)
            model_name = type(self.model).__name__
            # --- DECISION LOGIC ---

            # A. Hardware Override
            if 5 < flame_val < 500 and dht22_temp > 45:
                add_log(
                    f"   🔥 DECISION: [FIRE] Hardware Override (Flame:{flame_val}, Temp:{dht22_temp})\n"
                )
                return "Fire"

            # B. AI Confidence
            if fire_prob >= 0.80:
                add_log(
                    f"   🔥 DECISION: [FIRE] AI Confidence ({prob_percent}%) ({model_name})\n"
                )
                return "Fire"

            elif 0.40 <= fire_prob < 0.75:
                add_log(
                    f"   ⚠️ DECISION: [WARNING] AI Confidence ({prob_percent}%) ({model_name})\n"
                )
                return "Warning"

            # C. Gas Heuristic
            if methane > 800 or lpg > 800 or co > 100:
                add_log(
                    f"☣️ DECISION: [GAS LEAK] High PPM detected (M:{methane}, L:{lpg}, C:{co})\n"
                )
                return "Gas Leak"

            add_log(
                f"   ✅ DECISION: [SAFE] Confidence low ({prob_percent}%) ({model_name})\n"
            )
            return "Safe"

        except Exception as e:
            add_log(f"   ❌ Prediction Error: {e}\n")
            return "Safe"

    def get_active_model_info(self):
        if self.model:
            return str(self.model)
        return "No Model Loaded"
