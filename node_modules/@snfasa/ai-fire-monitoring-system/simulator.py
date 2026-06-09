import random
import time

import requests  # <--- The key difference (HTTP instead of MQTT)

# CONFIGURATION
DJANGO_URL = "http://127.0.0.1:8000/api/send-data/"

# IDs must match your Database IDs
SENSORS_CONFIG = [
    {"id": 1, "location": "Kitchen"},
    {"id": 2, "location": "Bedroom1"},
    {"id": 3, "location": "Bedroom2"},
    {"id": 4, "location": "Bedroom3"},
    {"id": 5, "location": "Living Room"},
]


# --- COPY OF YOUR VIRTUAL SENSOR LOGIC ---
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
        # 1% chance to start Warning
        if self.state == "Safe" and random.randint(0, 100) > 99:
            self.state = "Warning"
            self.fire_timer = 15
            print(f"\n⚠️  [{self.location}] WARNING STARTED (Gas Rising)!")

        # Warning can turn into Fire
        elif self.state == "Warning":
            self.fire_timer -= 1
            # 20% chance to ignite during warning
            if random.randint(0, 100) > 80:
                self.state = "Fire"
                self.fire_timer = 20
                print(f"\n🔥🔥🔥 [{self.location}] FIRE STARTED! 🔥🔥🔥")
            elif self.fire_timer <= 0:
                self.state = "Safe"
                print(f"✅ [{self.location}] Warning cleared.")

        elif self.state == "Fire":
            self.fire_timer -= 1
            if self.fire_timer <= 0:
                self.state = "Safe"
                print(f"🧯 [{self.location}] Fire Extinguished.")

        # --- DATA GENERATION ---
        if self.state == "Fire":
            # Fire Logic: Temp UP, Humidity DOWN, Gas UP, Flame DOWN
            self.temp += random.uniform(1.5, 3.0)
            self.humidity -= random.uniform(2.0, 4.0)
            self.methane = random.randint(800, 1500)
            self.co = random.randint(100, 300)
            self.flame_val = random.randint(100, 300)  # < 400 is Fire

        elif self.state == "Warning":
            # Warning Logic: Temp slight UP, Gas UP
            self.methane = random.randint(800, 1200)
            self.lpg = random.randint(800, 1200)
            self.co = random.randint(150, 250)
            self.temp += random.uniform(0.0, 0.2)
            self.humidity -= random.uniform(0.5, 1.0)
            self.flame_val = min(4095, self.flame_val + 50)

        else:
            # Safe Recovery Logic
            if self.temp > 28:
                self.temp -= 0.5
            if self.humidity < 60:
                self.humidity += 0.5
            elif self.humidity > 60:
                self.humidity -= 0.1

            if self.methane > 300:
                self.methane -= 50
            if self.lpg > 300:
                self.lpg -= 50
            if self.flame_val < 4095:
                self.flame_val += 50

        # Clamp values
        self.temp = round(max(0, min(100, self.temp)), 2)
        self.humidity = round(max(0, min(100, self.humidity)), 2)
        self.methane = max(0, self.methane)
        self.flame_val = min(4095, max(0, self.flame_val))

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


# --- MAIN LOOP (HTTP POST) ---
print(f"🚀 Simulation Running... Target: {DJANGO_URL}")
print("   (Simulating 5 sensors with random events)")

# Create virtual sensors
sensors = [VirtualSensor(c["id"], c["location"]) for c in SENSORS_CONFIG]

while True:
    for s in sensors:
        data = s.update()

        try:
            # SEND VIA HTTP POST
            # This triggers 'receive_sensor_data' in views.py
            response = requests.post(DJANGO_URL, json=data, timeout=1)

            # Formatting Output
            status_txt = "SAFE"
            if s.state == "Fire":
                status_txt = "FIRE"
            elif s.state == "Warning":
                status_txt = "WARN"

            # Print status line (overwrites previous line for cleanness)
            print(
                f"[{s.id}-{s.location[:3]}] {status_txt} | Gas:{data['methane']} | Temp:{data['dht22_temp']} | Flame:{data['flame_val']}"
            )

            # Check if Server Confirmed Fire
            if response.text == "1" and s.state != "Fire":
                print(f"🚨 SERVER ALERT CONFIRMED for Sensor {s.id}!")

        except requests.exceptions.ConnectionError:
            print(f"\n❌ Connection Failed for Sensor {s.id}. Is Django running?")
        except Exception as e:
            print(f"\n❌ Error: {e}")

        time.sleep(0.2)  # Small delay between sensor updates

    time.sleep(1)  # 1 second cycle
