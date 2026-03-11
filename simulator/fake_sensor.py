import time
import json
import random
import sys
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
TOPIC = "fire-system/sensor-data"

# IDs must match your Database IDs
SENSORS_CONFIG = [
    {"id": 1, "location": "Kitchen"},
    {"id": 2, "location": "Bedroom1"},
    {"id": 3, "location": "Bedroom2"},
    {"id": 4, "location": "Bedroom3"},
    {"id": 5, "location": "Living Room"},
    {"id": 70, "location": "Kitchen"},
    {"id": 71, "location": "Ruang Tamu"},
    {"id": 72, "location": "Bedroom1"},
    {"id": 73, "location": "Bedroom2"},
    {"id": 74, "location": "Bedroom3"},
    {"id": 75, "location": "Kitchen"},
    {"id": 76, "location": "Ruang Tamu"},
    {"id": 77, "location": "Bedroom1"},
    {"id": 78, "location": "Bedroom2"},
    {"id": 79, "location": "Bedroom3"}
]

class VirtualSensor:
    def __init__(self, sensor_id, location):
        self.id = sensor_id
        self.location = location
        self.state = "Safe"
        self.fire_timer = 0
        
        # Baselines
        self.temp = 28.0
        self.humidity = 60.0
        self.methane = 300
        self.lpg = 300
        self.co = 80
        self.air_quality = 90
        self.flame_val = 4095 

    def update(self):
        # --- STATE LOGIC ---
        # 2% chance to start Warning
        if self.state == "Safe" and random.randint(0, 100) > 98:
            self.state = "Warning"
            self.fire_timer = 15
            print(f"!!! [{self.location}] WARNING STARTED (Gas Rising) !!!")

        # Warning can turn into Fire
        elif self.state == "Warning":
            self.fire_timer -= 1
            if random.randint(0, 100) > 80: # Chance to ignite
                self.state = "Fire"
                self.fire_timer = 20
                print(f"!!! [{self.location}] FIRE STARTED !!!")
            elif self.fire_timer <= 0:
                self.state = "Safe"

        elif self.state == "Fire":
            self.fire_timer -= 1
            if self.fire_timer <= 0:
                self.state = "Safe"
                print(f"--- [{self.location}] Fire Extinguished ---")

        # --- DATA GENERATION ---
        if self.state == "Fire":
            # Fire Logic: Temp UP, Humidity DOWN, Gas UP
            self.temp += random.uniform(1.5, 3.0) 
            self.humidity -= random.uniform(2.0, 4.0) # <--- Humidity drops fast
            self.methane = random.randint(800, 1500)
            self.co = random.randint(100, 300)
            self.flame_val = random.randint(200, 600) 
            
        elif self.state == "Warning":
            # Warning Logic: Temp slight UP, Humidity slight DOWN
            self.methane = random.randint(800, 1200) 
            self.lpg = random.randint(800, 1200)
            self.co = random.randint(150, 250)
            self.temp += random.uniform(0.0, 0.2) 
            self.humidity -= random.uniform(0.5, 1.0) # <--- Humidity drops slowly
            self.flame_val = min(4095, self.flame_val + 50) 

        else:
            # Safe Recovery Logic
            if self.temp > 28: self.temp -= 0.5
            
            # Recover Humidity back to 60%
            if self.humidity < 60: 
                self.humidity += 0.5
            elif self.humidity > 60:
                self.humidity -= 0.1
                
            if self.methane > 300: self.methane -= 50
            self.flame_val = min(4095, self.flame_val + 50)

        # Clamp values to realistic ranges
        self.temp = round(max(0, min(100, self.temp)), 2)
        self.humidity = round(max(0, min(100, self.humidity)), 2)
        self.methane = max(0, self.methane)
        self.flame_val = max(0, self.flame_val)

        return {
            "sensor_id": self.id,
            "methane": int(self.methane),
            "lpg": int(self.lpg),
            "co": int(self.co),
            "air_quality": int(self.air_quality),
            "flame_val": int(self.flame_val),
            "dht22_temp": self.temp,
            "humidity": self.humidity,
        }

client = mqtt.Client()
client.connect(BROKER, 1883, 60)
sensors = [VirtualSensor(c['id'], c['location']) for c in SENSORS_CONFIG]

print("Simulating... (Ctrl+C to stop)")
while True:
    for s in sensors:
        data = s.update()
        client.publish(TOPIC, json.dumps(data))
        
        status_txt = "SAFE"
        if s.state == "Fire": 
            status_txt = "FIRE"
        elif s.state == "Warning": 
            status_txt = "WARN"
        
    print(f"[{s.id}] {status_txt} | Gas:{data['methane']} | "
      f"Temp:{data['dht22_temp']} | Hum:{data['humidity']}")
    time.sleep(0.5)
    time.sleep(1)