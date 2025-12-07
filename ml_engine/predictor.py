import pickle 
import os 
import numpy as np 

# location of the trained model file 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')

class FirePredictor:
    def __init__(self):
        self.model =None
        self.load_model()
        # change from number to text label for database 
        self.labels = {
            0:'Safe',
            1:'Fire',
            2:'Gas Leak'
        }
        
    def load_model(self):
        try:
            with open(MODEL_PATH, 'rb') as f :
                self.model = pickle.load(f)
            print("✅ Model loaded successfully.")
        except FileNotFoundError:
            print("❌ Model file not found. Please train the model first.")
            
    def predict(self, methane, lpg, co, air_quality, flame_val, dht22_temp, humidity):
        if self.model is None:
            return "System Error: Model not loaded."
        
        # Prepare the input data as a 2D array
        inputs = [[methane, lpg, co, air_quality, flame_val, dht22_temp, humidity]]
        
        # Perform prediction
        try:
            prediction_index =self.model.predict(inputs)[0]
            
            #result 
            return self.labels.get(prediction_index, "Unknown")
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            return "System Error: Prediction failed."