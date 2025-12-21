import json
import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand
from django.utils import timezone
from sensors.models import Sensor, SensorDataLog

# --- IMPORT YOUR NEW CLASS ---
from ml_engine.predictor import FirePredictor

class Command(BaseCommand):
    help = 'Connects to MQTT Broker, uses Trained AI Model, and saves data'

    def handle(self, *args, **kwargs):
        BROKER = "broker.emqx.io"
        PORT = 1883
        TOPIC = "fire-system/sensor-data"
        
        # --- INITIALIZE AI ENGINE ---
        self.stdout.write("Loading AI Model...")
        ai_engine = FirePredictor() # Load the pickle file once on startup

        def on_connect(client, userdata, flags, rc):
            self.stdout.write(self.style.SUCCESS(f'Connected. Listening for Sensor Data...'))
            client.subscribe(TOPIC)

        def on_message(client, userdata, msg):
            try:
                # 1. Parse Data
                payload = json.loads(msg.payload.decode())
                
                # 2. Get Sensor ID
                try:
                    sensor_instance = Sensor.objects.get(id=payload['sensor_id'])
                except Sensor.DoesNotExist:
                    print(f"Sensor {payload['sensor_id']} not found.")
                    return

                # --- 3. PASS TO REAL AI ENGINE ---
                # We extract the specific features your model needs
                prediction = ai_engine.predict(
                    methane=payload.get('methane', 0),
                    lpg=payload.get('lpg', 0),
                    co=payload.get('co', 0),
                    air_quality=payload.get('air_quality', 0),
                    flame_val=payload.get('flame_val', 1000),
                    dht22_temp=payload.get('dht22_temp', 25.0),
                    humidity=payload.get('humidity', 50.0)
                )

                # 4. Save to Database (Using the AI-Predicted Status)
                SensorDataLog.objects.create(
                    sensor=sensor_instance,
                    methane=payload.get('methane'),
                    lpg=payload.get('lpg'),
                    co=payload.get('co'),
                    air_quality=payload.get('air_quality'),
                    flame_val=payload.get('flame_val'),
                    dht22_temp=payload.get('dht22_temp'),
                    humidity=payload.get('humidity'),
                    status=prediction  # <--- SAVING THE AI RESULT ('Safe', 'Fire', 'Gas Leak')
                )
                
                # Visual Feedback
                if prediction == 'Fire':
                    msg_style = self.style.ERROR 
                elif prediction == 'Gas Leak':
                    msg_style = self.style.WARNING
                else:
                    msg_style = self.style.SUCCESS

                self.stdout.write(msg_style(f"[{timezone.now().strftime('%H:%M:%S')}] AI Prediction: {prediction} | Inputs: Temp={payload['dht22_temp']}, Flame={payload['flame_val']}, Humidity={payload['humidity']}, Methane={payload['methane']}, LPG={payload['lpg']}, CO={payload['co']}, Air Quality={payload['air_quality']},  | Sensor ID: {payload['sensor_id']} "))

            except Exception as e:
                print(f"Error: {e}")

        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, PORT, 60)
        client.loop_forever()