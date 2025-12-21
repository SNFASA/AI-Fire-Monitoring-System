import time
import json
import random
import sys

# Try to import paho-mqtt, warn if missing
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: 'paho-mqtt' library not found.")
    print("Please run: pip install paho-mqtt")
    sys.exit(1)

# --- CONFIGURATION ---
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "fire-system/sensor-data"
SENSOR_DB_ID = 1  # MUST match the ID of the sensor you created in Django

# --- SETUP MQTT CLIENT ---
client = mqtt.Client()

try:
    client.connect(BROKER, PORT, 60)
    print(f"Connected to Broker: {BROKER}")
    print(f"Publishing to Topic: {TOPIC}")
    print("Press Ctrl+C to stop...")
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

# --- SIMULATION LOOP ---
while True:
    try:
        # 1. Generate Fake Data
        methane = random.randint(200, 800)       # Normal: 200-500
        lpg = random.randint(200, 800)
        co = random.randint(50, 200)
        air_quality = random.randint(80, 150)
        
        # Flame sensor (Analog): Low value often means FIRE detected
        flame_val = random.randint(100, 4095) 
        
        dht22_temp = round(random.uniform(25.0, 65.0), 2)
        humidity = round(random.uniform(40.0, 90.0), 2)

        # 2. Determine Status Logic (Simple rules)
        status = "Safe"
        if flame_val < 500 or dht22_temp > 58.0:
            status = "Fire"
        elif methane > 600 or lpg > 600:
            status = "GasLeak"

        # 3. Create Payload
        payload = {
            "sensor_id": SENSOR_DB_ID,
            "methane": methane,
            "lpg": lpg,
            "co": co,
            "air_quality": air_quality,
            "flame_val": flame_val,
            "dht22_temp": dht22_temp,
            "humidity": humidity,
            "status": status
        }

        # 4. Send Data
        client.publish(TOPIC, json.dumps(payload))
        
        # Visual feedback for you
        print(f"Sent: [Status: {status}] [Temp: {dht22_temp}C] [Flame: {flame_val}] [Methane: {methane}] [LPG: {lpg}] [CO: {co}] [Air Quality: {air_quality}] [Humidity: {humidity}]")
        
        # Wait 3 seconds
        time.sleep(3)

    except KeyboardInterrupt:
        print("\nSimulation stopped.")
        break