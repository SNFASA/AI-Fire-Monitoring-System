import json
import random
import time

import requests

# Point this directly to your local Django API
API_URL = "http://127.0.0.1:8000/api/send-data/"

# IDs must match existing sensors in your PostgreSQL Database
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
    {"id": 79, "location": "Bedroom3"},
]


class VirtualESP32:
    def __init__(self, sensor_id, location):
        self.id = sensor_id
        self.location = location
        self.state = "Safe"
        self.fire_timer = 0

        # Baselines matching ESP32 12-bit ADC (0-4095) normal room conditions
        self.temp = 30.0
        self.humidity = 60.0
        self.methane = 300
        self.lpg = 300
        self.co = 150
        self.air_quality = 200
        self.flame_val = 4095  # Active-LOW: 4095 means NO FLAME

    def update(self):
        # --- STATE MACHINE LOGIC ---
        if self.state == "Safe" and random.randint(0, 100) > 95:
            # 5% chance to trigger a Gas Leak / Warning
            self.state = "Warning"
            self.fire_timer = 15
            print(f"⚠️ [{self.location}] GAS LEAK DETECTED (Levels Rising)...")

        elif self.state == "Warning":
            self.fire_timer -= 1
            if random.randint(0, 100) > 70:
                # 30% chance gas leak turns into an active fire
                self.state = "Fire"
                self.fire_timer = 20
                print(f"🔥 [{self.location}] FIRE IGNITED!")
            elif self.fire_timer <= 0:
                self.state = "Safe"

        elif self.state == "Fire":
            self.fire_timer -= 1
            if self.fire_timer <= 0:
                self.state = "Safe"
                print(f"💧 [{self.location}] Fire Extinguished. Returning to Safe.")

        # --- REALISTIC HARDWARE METRICS ---
        if self.state == "Fire":
            # Temp > 45 triggers your AI Fire Override, Flame drops to ~400
            self.temp = min(80.0, self.temp + random.uniform(5.0, 10.0))
            self.humidity = max(20.0, self.humidity - random.uniform(2.0, 5.0))
            self.methane = random.randint(1500, 3000)
            self.lpg = random.randint(1500, 3000)
            self.co = random.randint(1200, 2500)
            self.flame_val = random.randint(100, 600)  # LOW = Flame detected!

        elif self.state == "Warning":
            # Gas spikes, Temp stays normal, Flame stays high (NO FLAME)
            self.methane = random.randint(1200, 2000)
            self.lpg = random.randint(1200, 2000)
            self.co = random.randint(800, 1500)
            self.temp += random.uniform(0.1, 0.5)
            self.flame_val = min(4095, self.flame_val + 50)

        else:
            # Safe Recovery (Slowly return to baseline)
            self.temp = max(30.0, self.temp - 2.0)
            self.humidity = min(60.0, self.humidity + 2.0)
            self.methane = max(300, self.methane - 200)
            self.lpg = max(300, self.lpg - 200)
            self.co = max(150, self.co - 100)
            self.flame_val = min(4095, self.flame_val + 500)

        # Assemble Exact Payload Your Django API Expects
        return {
            "sensor_id": self.id,
            "methane": int(self.methane),
            "lpg": int(self.lpg),
            "co": int(self.co),
            "air_quality": int(self.air_quality),
            "flame_val": int(self.flame_val),
            "dht22_temp": round(self.temp, 2),
            "humidity": round(self.humidity, 2),
        }


if __name__ == "__main__":
    sensors = [VirtualESP32(c["id"], c["location"]) for c in SENSORS_CONFIG]
    print("🚀 Booting Virtual ESP32 Swarm... (Ctrl+C to stop)")

    while True:
        for s in sensors:
            payload = s.update()

            try:
                # Send data to Django just like the physical hardware!
                response = requests.post(API_URL, json=payload, timeout=5)

                # Determine display color
                status_txt = "SAFE"
                if s.state == "Fire":
                    status_txt = "FIRE"
                elif s.state == "Warning":
                    status_txt = "WARN"

                print(
                    f"[{s.id}] {status_txt} | Gas:{payload['methane']} | "
                    f"Temp:{payload['dht22_temp']} | Flame:{payload['flame_val']} | "
                    f"Server: {response.status_code}"
                )
            except requests.exceptions.RequestException as e:
                print(f"[{s.id}] ❌ Connection Failed: Is Django running?")

        time.sleep(3)  # Send batch every 3 seconds
