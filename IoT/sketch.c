/* ------------------------------------------------------
  ESP32 Multi-sensor Fire/Gas Monitor -> Firebase (Persistent logging)
  - MQ-4 (CH4), MQ-5 (NG/LPG), MQ-7 (CO), MQ-135 (Air quality)
  - KY-026 (flame) analog + digital
  - DHT22
  - TMP102 via TCA9548A ch0
  - ADS1115 via TCA9548A ch0 (optional)
  - Device ID persisted in Preferences (NVS). Can set via Serial "setid <ID>".
  - Auto-calibration of R0 on first run (clean air) or via "cal" Serial command.
  - Sends:
     POST -> /devices/<DEVICE_ID>/history.json  (append)
     PUT  -> /devices/<DEVICE_ID>/latest.json   (latest snapshot)
  - Requires libraries: Adafruit_ADS1015 (or ADS1115), DHT
  - IMPORTANT: set WIFI_SSID/WIFI_PASS/FIREBASE_URL/FIREBASE_AUTH below
  ------------------------------------------------------ */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_ADS1015.h>
#include "DHT.h"
#include <Preferences.h>
#include <time.h>

Preferences prefs;
Adafruit_ADS1115 ads;
DHT dht(27, DHT22); // DHT on GPIO27

// ========== CONFIG - EDIT THESE ==========
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASS";
const char* FIREBASE_URL = "https://your-project-id.firebaseio.com"; // no trailing slash
const char* FIREBASE_AUTH = "YOUR_DB_SECRET_OR_TOKEN"; // leave empty if not used

const String PREF_NAMESPACE = "iot_cfg";
const String PREF_KEY_DEVICEID = "device_id";
const String PREF_KEY_R0_MQ4 = "r0_mq4";
const String PREF_KEY_R0_MQ5 = "r0_mq5";
const String PREF_KEY_R0_MQ7 = "r0_mq7";
const String PREF_KEY_R0_MQ135 = "r0_mq135";

String DEVICE_ID = "ESP32_UNKNOWN"; // default; will load from prefs if set

// Publish interval
const unsigned long PUBLISH_INTERVAL = 5000UL; // ms

// Pins
const int PIN_MQ5_ADC  = 35;
const int PIN_MQ7_ADC  = 32;
const int PIN_MQ4_ADC  = 34;
const int PIN_MQ135_ADC = 33;
const int PIN_KY_A0    = 25;
const int PIN_KY_D0    = 4;
const int PIN_SIG_POT  = 36;
const int PIN_BUZZER   = 23;
const int PIN_LED      = 26;
const int PIN_HEATER_MOSFET = 18;
const int PIN_MOSFET2  = 19;

// ADC / voltage settings
const float VCC_SENSOR = 5.0;
const float ADC_REF = 3.3;
const int ADC_RES = 4095;
float VOLT_DIVIDER_RATIO = 0.666; // change if your divider different (e.g., 3.3/5 = 0.666)

// RL values (ohm) - change if known from your module
float RL_MQ135 = 10000.0;
float RL_MQ7   = 10000.0;
float RL_MQ4   = 20000.0; // guess; update if you know
float RL_MQ5   = 20000.0; // guess; update if you know

// Clean air ratios (Rs/R0) from datasheets (used for auto-calibration)
const float CA_MQ4   = 4.4;
const float CA_MQ5   = 6.5;
const float CA_MQ7   = 27.0;
const float CA_MQ135 = 3.6;

// Curve params (log-log): log10(ppm) = m*log10(Rs/R0) + c
struct Curve { float m; float c; };
Curve CURVE_MQ4   = { -0.318, 1.133 };
Curve CURVE_MQ5   = { -0.440, 1.800 };
Curve CURVE_MQ7   = { -0.770, 1.699 };
Curve CURVE_MQ135 = { -0.420, 1.920 };

// runtime R0 values
float R0_MQ4 = NAN, R0_MQ5 = NAN, R0_MQ7 = NAN, R0_MQ135 = NAN;
bool autoCalibrated = false;

// helpers
void tca_select(uint8_t ch) { if (ch>7) return; Wire.beginTransmission(0x70); Wire.write(1<<ch); Wire.endTransmission(); }
float adcToVolt(int raw) { return ((float)raw / (float)ADC_RES) * ADC_REF; }
float vModuleFromAdc(float vAdc) { if (VOLT_DIVIDER_RATIO <= 0.0001) return vAdc; return vAdc / VOLT_DIVIDER_RATIO; }
float computeRsFromV(float vModule, float rLoad) { if (vModule <= 0.0001) return 1e9; return rLoad * ((VCC_SENSOR - vModule) / vModule); }
float computePPM(float Rs, float R0, Curve curve) {
  if (!isfinite(R0) || R0<=0 || Rs<=0) return NAN;
  float ratio = Rs / R0;
  float logRatio = log10(ratio);
  float logppm = (logRatio - curve.c) / curve.m;
  float ppm = pow(10.0, logppm);
  return ppm;
}

// ========== Networking & Firebase helpers ==========
String firebasePost(const String &path, const String &jsonPayload) {
  // POST -> path.json will create unique key (push)
  String url = FIREBASE_URL + path + ".json";
  if (strlen(FIREBASE_AUTH) > 0) url += "?auth=" + String(FIREBASE_AUTH);

  WiFiClientSecure *client = new WiFiClientSecure();
  client->setInsecure();
  HTTPClient https;
  https.begin(*client, url);
  https.addHeader("Content-Type", "application/json");
  int code = https.POST(jsonPayload);
  String resp = "";
  if (code > 0) {
    resp = https.getString();
  } else {
    Serial.printf("[HTTP] POST failed: %s\n", https.errorToString(code).c_str());
  }
  https.end();
  delete client;
  return resp; // contains response with name key if success
}

bool firebasePut(const String &path, const String &jsonPayload) {
  String url = FIREBASE_URL + path + ".json";
  if (strlen(FIREBASE_AUTH) > 0) url += "?auth=" + String(FIREBASE_AUTH);
  WiFiClientSecure *client = new WiFiClientSecure();
  client->setInsecure();
  HTTPClient https;
  https.begin(*client, url);
  https.addHeader("Content-Type", "application/json");
  int code = https.PUT(jsonPayload);
  https.end();
  delete client;
  return (code >= 200 && code < 300);
}

// get ISO8601 timestamp using NTP (Malaysia UTC+08:00)
void setupTime() {
  // set timezone for Malaysia: POSIX TZ is backwards: UTC+8 => "UTC-8"
  setenv("TZ", "UTC-8", 1);
  tzset();
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}

String isoTimestamp() {
  time_t now = time(nullptr);
  if (now < 1600000000) return String(millis()); // no time yet
  struct tm timeinfo;
  localtime_r(&now, &timeinfo);
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S%z", &timeinfo); // e.g., 2025-11-19T18:00:05+0800
  return String(buf);
}

// Serial command processing
void processSerialCommands(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  if (cmd.equalsIgnoreCase("cal")) {
    Serial.println("Serial: Starting manual calibration (clean air required)...");
    autoCalibrated = false; // force calibration
  } else if (cmd.startsWith("setid ")) {
    String id = cmd.substring(6);
    id.trim();
    if (id.length()>0) {
      DEVICE_ID = id;
      prefs.begin(PREF_NAMESPACE.c_str(), false);
      prefs.putString(PREF_KEY_DEVICEID.c_str(), DEVICE_ID);
      prefs.end();
      Serial.printf("Device ID set to: %s\n", DEVICE_ID.c_str());
    }
  } else if (cmd.equalsIgnoreCase("showid")) {
    Serial.printf("Device ID: %s\n", DEVICE_ID.c_str());
  } else if (cmd.equalsIgnoreCase("clearr0")) {
    prefs.begin(PREF_NAMESPACE.c_str(), false);
    prefs.remove(PREF_KEY_R0_MQ4.c_str());
    prefs.remove(PREF_KEY_R0_MQ5.c_str());
    prefs.remove(PREF_KEY_R0_MQ7.c_str());
    prefs.remove(PREF_KEY_R0_MQ135.c_str());
    prefs.end();
    R0_MQ4 = R0_MQ5 = R0_MQ7 = R0_MQ135 = NAN;
    autoCalibrated = false;
    Serial.println("Cleared stored R0, next cycle will recalibrate.");
  } else {
    Serial.println("Unknown command. Commands: cal | setid <ID> | showid | clearr0");
  }
}

// Auto-calibration routine (clean air). Runs when R0 missing or forced.
void tryAutoCalibrate() {
  if (autoCalibrated) return;
  // run only after a warm-up / wait
  static unsigned long started = millis();
  if (millis() - started < 12000) return; // wait ~12s

  Serial.println("=== Starting MQ Auto-calibration (ensure CLEAN AIR) ===");
  const int SAMPLES = 100;
  const int S_DELAY = 200;
  double sum4=0,sum5=0,sum7=0,sum135=0;
  int v4cnt=0,v5cnt=0,v7cnt=0,v135cnt=0;

  for (int i=0;i<SAMPLES;i++) {
    int r4 = readADCaveraged(PIN_MQ4_ADC,3,3);
    int r5 = readADCaveraged(PIN_MQ5_ADC,3,3);
    int r7 = readADCaveraged(PIN_MQ7_ADC,3,3);
    int r135 = readADCaveraged(PIN_MQ135_ADC,3,3);

    float v4 = vModuleFromAdc(adcToVolt(r4));
    float v5 = vModuleFromAdc(adcToVolt(r5));
    float v7 = vModuleFromAdc(adcToVolt(r7));
    float v135 = vModuleFromAdc(adcToVolt(r135));

    float Rs4 = computeRsFromV(v4, RL_MQ4);
    float Rs5 = computeRsFromV(v5, RL_MQ5);
    float Rs7 = computeRsFromV(v7, RL_MQ7);
    float Rs135 = computeRsFromV(v135, RL_MQ135);

    if (isfinite(Rs4) && Rs4<1e8) { sum4 += Rs4; v4cnt++; }
    if (isfinite(Rs5) && Rs5<1e8) { sum5 += Rs5; v5cnt++; }
    if (isfinite(Rs7) && Rs7<1e8) { sum7 += Rs7; v7cnt++; }
    if (isfinite(Rs135) && Rs135<1e8) { sum135 += Rs135; v135cnt++; }

    delay(S_DELAY);
  }

  prefs.begin(PREF_NAMESPACE.c_str(), false);
  if (v4cnt>0) {
    R0_MQ4 = (sum4 / v4cnt) / CA_MQ4;
    prefs.putFloat(PREF_KEY_R0_MQ4.c_str(), R0_MQ4);
  }
  if (v5cnt>0) {
    R0_MQ5 = (sum5 / v5cnt) / CA_MQ5;
    prefs.putFloat(PREF_KEY_R0_MQ5.c_str(), R0_MQ5);
  }
  if (v7cnt>0) {
    R0_MQ7 = (sum7 / v7cnt) / CA_MQ7;
    prefs.putFloat(PREF_KEY_R0_MQ7.c_str(), R0_MQ7);
  }
  if (v135cnt>0) {
    R0_MQ135 = (sum135 / v135cnt) / CA_MQ135;
    prefs.putFloat(PREF_KEY_R0_MQ135.c_str(), R0_MQ135);
  }
  prefs.end();

  Serial.printf("Auto-cal done. R0s: MQ4=%.2f MQ5=%.2f MQ7=%.2f MQ135=%.2f\n",
                R0_MQ4, R0_MQ5, R0_MQ7, R0_MQ135);
  autoCalibrated = true;
}

// Setup
void setup() {
  Serial.begin(115200);
  delay(200);
  Wire.begin(); // default SDA=21 SCL=22
  dht.begin();
  ads.begin();

  // pins
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_KY_D0, INPUT);
  pinMode(PIN_HEATER_MOSFET, OUTPUT);
  digitalWrite(PIN_HEATER_MOSFET, HIGH);

  // ADC attenuation
  analogSetPinAttenuation(PIN_MQ5_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_MQ7_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_MQ4_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_MQ135_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_KY_A0, ADC_11db);
  analogSetPinAttenuation(PIN_SIG_POT, ADC_11db);

  // preferences load
  prefs.begin(PREF_NAMESPACE.c_str(), false);
  DEVICE_ID = prefs.getString(PREF_KEY_DEVICEID.c_str(), DEVICE_ID).c_str();
  R0_MQ4 = prefs.getFloat(PREF_KEY_R0_MQ4.c_str(), NAN);
  R0_MQ5 = prefs.getFloat(PREF_KEY_R0_MQ5.c_str(), NAN);
  R0_MQ7 = prefs.getFloat(PREF_KEY_R0_MQ7.c_str(), NAN);
  R0_MQ135 = prefs.getFloat(PREF_KEY_R0_MQ135.c_str(), NAN);
  prefs.end();

  // WiFi
  Serial.printf("Connecting WiFi '%s' ...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) { delay(250); Serial.print("."); tries++; }
  if (WiFi.status()==WL_CONNECTED) Serial.printf("\nWiFi connected: %s\n", WiFi.localIP().toString().c_str());
  else Serial.println("\nWiFi failed - continuing offline");

  // NTP/time
  setupTime();

  Serial.printf("Device ID: %s\n", DEVICE_ID.c_str());
  Serial.println("Serial commands: cal | setid <ID> | showid | clearr0");
  Serial.println("Startup complete.");
}

// Read averaged ADC
int readADCaveraged(int gpioPin, int samples = 6, int delayMs = 3) {
  long sum=0;
  for (int i=0;i<samples;i++){ sum += analogRead(gpioPin); delay(delayMs); }
  return (int)(sum/samples);
}

// Main loop
unsigned long lastPublish = 0;
void loop() {
  // Serial commands
  if (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    processSerialCommands(s);
  }

  // Attempt auto-calibration if needed
  if (!autoCalibrated && (isnan(R0_MQ4) || isnan(R0_MQ5) || isnan(R0_MQ7) || isnan(R0_MQ135))) {
    tryAutoCalibrate();
  }

  unsigned long now = millis();
  if (now - lastPublish < PUBLISH_INTERVAL) {
    delay(10);
    return;
  }
  lastPublish = now;

  // read sensors
  float hum = dht.readHumidity();
  float t_dht = dht.readTemperature();
  float t_tmp102 = 0.0;
  // read TMP102
  tca_select(0);
  // Read TMP102 manually (as earlier helper). Minimal checks:
  Wire.beginTransmission(0x48);
  Wire.write(0x00);
  if (Wire.endTransmission(false)==0 && Wire.requestFrom((uint8_t)0x48,(uint8_t)2)) {
    uint8_t msb = Wire.read(); uint8_t lsb = Wire.read();
    int16_t raw = ((msb<<8)|lsb) >>4; if (raw & 0x800) raw |= 0xF000;
    t_tmp102 = raw * 0.0625;
  } else t_tmp102 = NAN;

  int raw_mq5  = readADCaveraged(PIN_MQ5_ADC,6,3);
  int raw_mq7  = readADCaveraged(PIN_MQ7_ADC,6,3);
  int raw_mq4  = readADCaveraged(PIN_MQ4_ADC,6,3);
  int raw_mq135= readADCaveraged(PIN_MQ135_ADC,6,3);
  int raw_ky_a0= readADCaveraged(PIN_KY_A0,6,3);
  int raw_pot  = readADCaveraged(PIN_SIG_POT,6,3);
  int ky_d0    = digitalRead(PIN_KY_D0);

  // ADS1115 optional read (ch0,ch1)
  tca_select(0);
  int16_t ads0 = ads.readADC_SingleEnded(0);
  int16_t ads1 = ads.readADC_SingleEnded(1);

  // convert -> vModule -> Rs
  float v_mq4_adc = adcToVolt(raw_mq4);
  float v_mq5_adc = adcToVolt(raw_mq5);
  float v_mq7_adc = adcToVolt(raw_mq7);
  float v_mq135_adc = adcToVolt(raw_mq135);
  float v_ky_adc = adcToVolt(raw_ky_a0);

  float v_mq4_mod = vModuleFromAdc(v_mq4_adc);
  float v_mq5_mod = vModuleFromAdc(v_mq5_adc);
  float v_mq7_mod = vModuleFromAdc(v_mq7_adc);
  float v_mq135_mod = vModuleFromAdc(v_mq135_adc);
  float v_ky_mod = vModuleFromAdc(v_ky_adc);

  float Rs4 = computeRsFromV(v_mq4_mod, RL_MQ4);
  float Rs5 = computeRsFromV(v_mq5_mod, RL_MQ5);
  float Rs7 = computeRsFromV(v_mq7_mod, RL_MQ7);
  float Rs135 = computeRsFromV(v_mq135_mod, RL_MQ135);

  // compute ppm if R0 present
  float ppm4 = isnan(R0_MQ4) ? NAN : computePPM(Rs4, R0_MQ4, CURVE_MQ4);
  float ppm5 = isnan(R0_MQ5) ? NAN : computePPM(Rs5, R0_MQ5, CURVE_MQ5);
  float ppm7 = isnan(R0_MQ7) ? NAN : computePPM(Rs7, R0_MQ7, CURVE_MQ7);
  float ppm135 = isnan(R0_MQ135) ? NAN : computePPM(Rs135, R0_MQ135, CURVE_MQ135);

  // determine alarm (use ppm if available else raw thresholds)
  bool alarm = false;
  const float TH_CH4 = 500.0, TH_LPG = 500.0, TH_CO = 50.0, TH_AIRQ = 300.0;
  if (!isnan(ppm4) && ppm4 > TH_CH4) alarm = true;
  if (!isnan(ppm5) && ppm5 > TH_LPG) alarm = true;
  if (!isnan(ppm7) && ppm7 > TH_CO) alarm = true;
  if (!isnan(ppm135) && ppm135 > TH_AIRQ) alarm = true;
  // fallback raw
  if (raw_ky_a0 < 1200) alarm = true;
  if (ky_d0 == LOW) alarm = true;

  if (alarm) { digitalWrite(PIN_LED, HIGH); digitalWrite(PIN_BUZZER, HIGH); }
  else { digitalWrite(PIN_LED, LOW); digitalWrite(PIN_BUZZER, LOW); }

  // Build JSON payload
  String ts = isoTimestamp();
  // Build payload manually (avoid String concat explosion) - but okay for moderate size
  char buf[1400];
  snprintf(buf, sizeof(buf),
    "{"
      "\"ts\":\"%s\",\"device\":\"%s\","
      "\"dht_temp\":%.2f,\"dht_hum\":%.2f,\"tmp102\":%.2f,"
      "\"mq4_raw\":%d,\"mq5_raw\":%d,\"mq7_raw\":%d,\"mq135_raw\":%d,"
      "\"mq4_rs\":%.2f,\"mq5_rs\":%.2f,\"mq7_rs\":%.2f,\"mq135_rs\":%.2f,"
      "\"mq4_ppm\":%.2f,\"mq5_ppm\":%.2f,\"mq7_ppm\":%.2f,\"mq135_ppm\":%.2f,"
      "\"ky_a0\":%d,\"ky_d0\":%d,\"ads0\":%d,\"ads1\":%d,\"pot\":%d,\"alarm\":%d"
    "}",
    ts.c_str(), DEVICE_ID.c_str(),
    isnan(t_dht)?NAN:t_dht, isnan(hum)?NAN:hum, isnan(t_tmp102)?NAN:t_tmp102,
    raw_mq4, raw_mq5, raw_mq7, raw_mq135,
    Rs4, Rs5, Rs7, Rs135,
    isnan(ppm4)?-1.0:ppm4, isnan(ppm5)?-1.0:ppm5, isnan(ppm7)?-1.0:ppm7, isnan(ppm135)?-1.0:ppm135,
    raw_ky_a0, ky_d0, ads0, ads1, raw_pot, alarm?1:0
  );

  String payload = String(buf);

  // 1) Append to /devices/<DEVICE_ID>/history  (POST to create unique entry)
  String histPath = "/devices/" + DEVICE_ID + "/history";
  String resp = firebasePost(histPath, payload);
  // optionally parse response to get key (not required)

  // 2) Update latest snapshot via PUT
  String latestPath = "/devices/" + DEVICE_ID + "/latest";
  bool okLatest = firebasePut(latestPath, payload);

  // Serial debug
  Serial.println("Published:");
  Serial.println(payload);
  delay(10);
}