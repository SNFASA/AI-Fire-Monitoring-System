import pandas as pd
import numpy as np

# Setup
rng = np.random.default_rng(seed=42)
total_samples = 90000

# === 1. DEFINE PROPORTIONS ===
n_safe = int(total_samples * 0.80)
n_fire = int(total_samples * 0.10)
n_gas = int(total_samples * 0.10)


# === 2. HELPER FUNCTION ===
def generate_sensor_readings(n, base_val, variation):
    readings = rng.normal(loc=base_val, scale=variation, size=n)
    return np.clip(readings, 0, 4095).astype(int)


# Scenario A: Safe
safe_data = pd.DataFrame(
    {
        "methane": generate_sensor_readings(n_safe, 300, 50),
        "lpg": generate_sensor_readings(n_safe, 300, 50),
        "co": generate_sensor_readings(n_safe, 150, 30),
        "air_quality": generate_sensor_readings(n_safe, 400, 100),
        "flame_val": generate_sensor_readings(n_safe, 4000, 50),
        "dht22_temp": generate_sensor_readings(n_safe, 28, 3),
        "humidity": generate_sensor_readings(n_safe, 60, 10),
        "status": 0,
    }
)

# Scenario B: Fire
fire_data = pd.DataFrame(
    {
        "methane": generate_sensor_readings(n_fire, 600, 100),
        "lpg": generate_sensor_readings(n_fire, 500, 100),
        "co": generate_sensor_readings(n_fire, 1500, 300),
        "air_quality": generate_sensor_readings(n_fire, 3000, 500),
        "flame_val": generate_sensor_readings(n_fire, 400, 200),
        "dht22_temp": generate_sensor_readings(n_fire, 65, 10),
        "humidity": generate_sensor_readings(n_fire, 30, 10),
        "status": 1,
    }
)

# Scenario C: Gas Leak
gas_data = pd.DataFrame(
    {
        "methane": generate_sensor_readings(n_gas, 3000, 400),
        "lpg": generate_sensor_readings(n_gas, 3200, 400),
        "co": generate_sensor_readings(n_gas, 2800, 400),
        "air_quality": generate_sensor_readings(n_gas, 800, 100),
        "flame_val": generate_sensor_readings(n_gas, 4000, 50),
        "dht22_temp": generate_sensor_readings(n_gas, 28, 3),
        "humidity": generate_sensor_readings(n_gas, 60, 10),
        "status": 2,
    }
)

# === SAVE ===
df = pd.concat([safe_data, fire_data, gas_data])
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

print(f"Generated {len(df)} rows.")
print(df["status"].value_counts())


df.to_csv("sensor_data.csv", index=False)
print("Success! File saved as 'sensor_data.csv'")
