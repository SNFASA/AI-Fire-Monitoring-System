/*
  Fire Detector — ESP32 firmware (v2: adds MQ-5)
  Sensors: MQ-4, MQ-5, MQ-7, MQ-135, DHT22, IR Flame, Buzzer, Red LED
  Backend: Django REST endpoint (PostgreSQL), JSON over HTTP
  Logic: Local weighted scoring + server override (hybrid)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ============== USER CONFIG ==============
const char* WIFI_SSID     = "azani66 5G";
const char* WIFI_PASSWORD = "";

// Django REST endpoint. Use your PC's LAN IP (e.g., 192.168.1.105) when ESP32 is on Wi-Fi.
// Make sure Django runs with: python manage.py runserver 0.0.0.0:8000
const char* SERVER_URL    = "http://192.168.1.105:8000/api/sensor-data/";
const char* DEVICE_ID     = "fire-node-01";
const char* API_TOKEN     = "REPLACE_WITH_TOKEN_FROM_DJANGO";

// ============== PIN MAP ==============
#define PIN_MQ4         34   // ADC1_CH6  (input-only)
#define PIN_MQ5         36   // ADC1_CH0  (input-only, VP)   <-- NEW
#define PIN_MQ7         35   // ADC1_CH7  (input-only)
#define PIN_MQ135       32   // ADC1_CH4
#define PIN_FLAME       33   // Digital input
#define PIN_DHT         4    // DHT22 data
#define PIN_BUZZER      26   // Active buzzer
#define PIN_LED         27   // Red LED via 220 ohm

#define DHT_TYPE        DHT22
DHT dht(PIN_DHT, DHT_TYPE);

// ============== TIMING ==============
const unsigned long WARMUP_MS       = 180000UL;  // 3 min MQ warm-up
const unsigned long SAMPLE_MS       = 2000UL;    // Sample + POST every 2s
const unsigned long TEMP_HISTORY_MS = 30000UL;   // Track temp rise over 30s

// ============== THRESHOLDS (tune after testing) ==============
// MQ analog values are 0-4095 (ESP32 12-bit ADC, after voltage divider)
const int   TH_MQ4        = 1500;   // Methane
const int   TH_MQ5        = 1500;   // LPG / natural gas             <-- NEW
const int   TH_MQ7        = 1200;   // CO
const int   TH_MQ135      = 1400;   // Air quality / smoke
const float TH_TEMP_HIGH  = 50.0;   // °C
const float TH_TEMP_RISE  = 5.0;    // °C rise within 30s
const int   ALARM_SCORE   = 70;     // Local alarm trigger

// ============== STATE ==============
unsigned long bootTime      = 0;
unsigned long lastSample    = 0;
bool          warmedUp      = false;
float         tempHistory[15];      // 30s / 2s = 15 samples
int           tempHistIdx   = 0;
bool          tempHistFull  = false;
bool          alarmActive   = false;
int           serverOverride = -1;  // -1 none, 0 off, 1 on

// ============== HELPERS ==============
void setLED(bool on)    { digitalWrite(PIN_LED, on ? HIGH : LOW); }
void setBuzzer(bool on) { digitalWrite(PIN_BUZZER, on ? HIGH : LOW); }

void blinkLED(int ms_on, int ms_off) {
  setLED(true);  delay(ms_on);
  setLED(false); delay(ms_off);
}

void connectWiFi() {
  Serial.printf("Connecting to %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWiFi OK - IP %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWiFi FAILED (will retry in loop)");
  }
}

// ============== SCORING ==============
// Weights (max possible = 50+25+25+30+20+25+15 = 190; alarm at 70)
int computeFireScore(int mq4, int mq5, int mq7, int mq135,
                     bool flame, float temp, float tempRise) {
  int score = 0;
  if (flame)               score += 50;
  if (mq7   > TH_MQ7)      score += 30;
  if (mq4   > TH_MQ4)      score += 25;
  if (mq5   > TH_MQ5)      score += 25;   // LPG leak weight
  if (mq135 > TH_MQ135)    score += 20;
  if (!isnan(temp)     && temp     > TH_TEMP_HIGH) score += 25;
  if (!isnan(tempRise) && tempRise > TH_TEMP_RISE) score += 15;
  return score;
}

float computeTempRise(float currentTemp) {
  if (isnan(currentTemp)) return 0;
  tempHistory[tempHistIdx] = currentTemp;
  tempHistIdx = (tempHistIdx + 1) % 15;
  if (tempHistIdx == 0) tempHistFull = true;

  if (!tempHistFull) return 0;
  float oldest = tempHistory[tempHistIdx];   // Next slot = oldest sample
  return currentTemp - oldest;
}

// ============== POST to Django ==============
bool postReading(int mq4, int mq5, int mq7, int mq135, bool flame,
                 float temp, float humidity, int score, bool localAlarm) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("No WiFi - skipping POST");
    connectWiFi();
    return false;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Token ") + API_TOKEN);

  StaticJsonDocument<448> doc;
  doc["device_id"]    = DEVICE_ID;
  doc["mq4"]          = mq4;
  doc["mq5"]          = mq5;          // <-- NEW
  doc["mq7"]          = mq7;
  doc["mq135"]        = mq135;
  doc["flame"]        = flame;
  doc["temperature"]  = isnan(temp)     ? 0 : temp;
  doc["humidity"]     = isnan(humidity) ? 0 : humidity;
  doc["score"]        = score;
  doc["local_alarm"]  = localAlarm;

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  if (code > 0) {
    String resp = http.getString();
    Serial.printf("POST %d  %s\n", code, resp.c_str());

    StaticJsonDocument<128> rdoc;
    DeserializationError err = deserializeJson(rdoc, resp);
    if (!err && rdoc.containsKey("fire_override")) {
      if (rdoc["fire_override"].is<bool>()) {
        serverOverride = rdoc["fire_override"].as<bool>() ? 1 : 0;
      } else {
        serverOverride = -1;
      }
    }
    http.end();
    return true;
  }
  Serial.printf("POST failed, code=%d\n", code);
  http.end();
  return false;
}

// ============== SETUP ==============
void setup() {
  Serial.begin(115200);
  delay(300);

  pinMode(PIN_FLAME, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  setBuzzer(false);
  setLED(false);

  analogReadResolution(12);            // 0-4095
  analogSetAttenuation(ADC_11db);      // Full ~0-3.3V range
  dht.begin();

  connectWiFi();

  Serial.println("MQ sensors warming up for 3 minutes...");
  bootTime = millis();
  while (millis() - bootTime < WARMUP_MS) {
    blinkLED(400, 400);                // Slow blink = warm-up
  }
  setLED(false);
  warmedUp = true;
  Serial.println("Warm-up complete. Starting normal operation.");
}

// ============== LOOP ==============
void loop() {
  if (millis() - lastSample < SAMPLE_MS) return;
  lastSample = millis();

  int   mq4    = analogRead(PIN_MQ4);
  int   mq5    = analogRead(PIN_MQ5);              // <-- NEW
  int   mq7    = analogRead(PIN_MQ7);
  int   mq135  = analogRead(PIN_MQ135);
  bool  flame  = (digitalRead(PIN_FLAME) == LOW);  // DO is active-LOW on most modules
  float temp   = dht.readTemperature();
  float hum    = dht.readHumidity();
  float rise   = computeTempRise(temp);

  int  score      = computeFireScore(mq4, mq5, mq7, mq135, flame, temp, rise);
  bool localAlarm = (score >= ALARM_SCORE);

  Serial.printf("MQ4=%d MQ5=%d MQ7=%d MQ135=%d FLAME=%d T=%.1f H=%.1f RISE=%.1f SCORE=%d\n",
                mq4, mq5, mq7, mq135, flame, temp, hum, rise, score);

  postReading(mq4, mq5, mq7, mq135, flame, temp, hum, score, localAlarm);

  bool finalAlarm;
  if      (serverOverride == 1) finalAlarm = true;
  else if (serverOverride == 0) finalAlarm = false;
  else                          finalAlarm = localAlarm;

  if (finalAlarm != alarmActive) {
    alarmActive = finalAlarm;
    setBuzzer(alarmActive);
    setLED(alarmActive);
    Serial.printf(">>> ALARM %s <<<\n", alarmActive ? "ON" : "OFF");
  }
}
