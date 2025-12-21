import json
import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand
from django.utils import timezone
from sensors.models import Sensor, SensorDataLog, UserProfile
from ml_engine.predictor import FirePredictor

class Command(BaseCommand):
    help = 'MQTT Listener with AI and Aggregation'

    def handle(self, *args, **kwargs):
        BROKER = "broker.emqx.io"
        TOPIC = "fire-system/sensor-data"
        self.ai_engine = FirePredictor()

        def update_house_status(sensor_instance):
            """ Checks all sensors in the house and updates UserProfile """
            try:
                house_profile = sensor_instance.owner 
                all_sensors = Sensor.objects.filter(owner=house_profile)
                
                new_house_status = "Safe"
                
                for s in all_sensors:
                    # Look at the last log to determine current status
                    last_log = s.readings.last()
                    st = str(last_log.status).lower() if last_log else "safe"
                    
                    if st == "fire":
                        new_house_status = "Fire"
                        break # Fire is priority
                    elif st in ["warning", "gas leak", "gasleak"]:
                        new_house_status = "Warning" # Map everything to 'Warning'
                
                # Update Profile if changed
                if house_profile.status != new_house_status:
                    house_profile.status = new_house_status
                    house_profile.save()
                    print(f"--> [UPDATE] House {house_profile.user.username} is now: {new_house_status}")
                    
            except Exception as e:
                print(f"Aggregation Error: {e}")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
                
                # 1. AI PREDICTION
                prediction = self.ai_engine.predict(
                    methane=payload.get('methane', 0),
                    lpg=payload.get('lpg', 0),
                    co=payload.get('co', 0),
                    air_quality=payload.get('air_quality', 0),
                    flame_val=payload.get('flame_val', 4095),
                    dht22_temp=payload.get('dht22_temp', 25.0),
                    humidity=payload.get('humidity', 50.0)
                )

                # 2. GET SENSOR & SAVE LOG
                sensor = Sensor.objects.get(id=payload['sensor_id'])
                
                SensorDataLog.objects.create(
                    sensor=sensor,
                    methane=payload.get('methane'),
                    lpg=payload.get('lpg'),
                    co=payload.get('co'),
                    air_quality=payload.get('air_quality'),
                    flame_val=payload.get('flame_val'),
                    dht22_temp=payload.get('dht22_temp'),
                    humidity=payload.get('humidity'),
                    status=prediction
                )
                
                # 3. UPDATE HOUSE STATUS
                update_house_status(sensor)

                # Console Feedback
                color = self.style.SUCCESS
                if prediction == 'Fire': color = self.style.ERROR
                elif prediction in ['Warning', 'Gas Leak']: color = self.style.WARNING
                self.stdout.write(color(f"[{timezone.now().time()}] Sensor {sensor.id}: {prediction}"))

            except Sensor.DoesNotExist:
                pass
            except Exception as e:
                print(f"Error: {e}")

        client = mqtt.Client()
        client.on_connect = lambda c, u, f, rc: c.subscribe(TOPIC)
        client.on_message = on_message
        client.connect(BROKER, 1883, 60)
        self.stdout.write("Connected to MQTT. Listening...")
        client.loop_forever()   