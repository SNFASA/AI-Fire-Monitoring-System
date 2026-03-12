/* ------------------------------------------------------
   ESP32 AI Fire Monitor -> Django ML Engine
   Logic: Send Data -> Receive "1" (Alarm) or "0" (Safe)
   ------------------------------------------------------ */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include "DHT.h"

// ========== 1. NETWORK SETTINGS (EDIT THIS!) ==========
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// REPLACE WITH YOUR LAPTOP'S IP ADDRESS (Check using 'ipconfig' in cmd)
// Example: "http://192.168.0.105:8000/api/send-data/"
const char* DJANGO_API_URL = "http://192.168.X.X:8000/api/send-data/";

// Match this ID to the ID in your Django Admin Panel (e.g., Sensor #1)
const int DEVICE_ID = 1; 

// ========== 2. PINS ==========
const int PIN_MQ5_ADC   = 35;
const int PIN_MQ7_ADC   = 32;
const int PIN_MQ4_ADC   = 34;
const int PIN_MQ135_ADC = 33;
const int PIN_KY_A0     = 25; // Flame Sensor
const int PIN_BUZZER    = 23;
const int PIN_LED       = 26;
DHT dht(27, DHT22); 

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  // Init Hardware
  dht.begin();
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  
  // IMPORTANT: Set ADC to read full 3.3V range (Required for Gas Sensors)
  analogSetAttenuation(ADC_11db);

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
}

void loop() {
  // 1. READ SENSORS
  float hum = dht.readHumidity();
  float temp = dht.readTemperature();
  int mq4 = analogRead(PIN_MQ4_ADC);
  int mq5 = analogRead(PIN_MQ5_ADC);
  int mq7 = analogRead(PIN_MQ7_ADC);
  int mq135 = analogRead(PIN_MQ135_ADC);
  int flame = analogRead(PIN_KY_A0);

  // Validate DHT (Check for NaN)
  if (isnan(hum) || isnan(temp)) { temp = 0; hum = 0; }

  // 2. PREPARE JSON PAYLOAD
  // We add 'sensor_id' so Django knows exactly which device this is.
  String jsonPayload = "{";
  jsonPayload += "\"sensor_id\": " + String(DEVICE_ID) + ","; 
  jsonPayload += "\"methane\": " + String(mq4) + ",";
  jsonPayload += "\"lpg\": " + String(mq5) + ",";
  jsonPayload += "\"co\": " + String(mq7) + ",";
  jsonPayload += "\"air_quality\": " + String(mq135) + ",";
  jsonPayload += "\"flame_val\": " + String(flame) + ",";
  jsonPayload += "\"dht22_temp\": " + String(temp) + ",";
  jsonPayload += "\"humidity\": " + String(hum);
  jsonPayload += "}";

  // 3. SEND TO DJANGO
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(DJANGO_API_URL);
    http.addHeader("Content-Type", "application/json");

    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("Sent. Server Command: ");
      Serial.println(response);

      // 4. CHECK ALARM COMMAND
      // If Server says "1", Turn ON. If "0", Turn OFF.
      if (response == "1") {
        Serial.println("!!! DANGER - ALARM ON !!!");
        digitalWrite(PIN_BUZZER, HIGH);
        digitalWrite(PIN_LED, HIGH);
      } else {
        digitalWrite(PIN_BUZZER, LOW);
        digitalWrite(PIN_LED, LOW);
      }
    } else {
      Serial.print("Error sending: ");
      Serial.println(httpResponseCode);
    }
    http.end();
  } else {
    Serial.println("WiFi Disconnected!");
  }

  delay(2000); // Wait 2 seconds before next reading
}