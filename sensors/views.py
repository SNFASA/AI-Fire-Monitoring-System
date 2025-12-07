from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
import json
from .models import Sensor, SensorDataLog
from ml_engine.predictor import FirePredictor
from django.core.serializers.json import DjangoJSONEncoder

# Init brain once
predictor = FirePredictor()

@csrf_exempt
def receive_sensor_data(request):
    if request.method == 'POST':
        try:
            # 1. Get data from ESP32
            data = json.loads(request.body)
            
            # 2. Extract values (Default to 0)
            methane = data.get('methane', 0) 
            lpg = data.get('lpg', 0)
            co = data.get('co', 0)
            air_quality = data.get('air_quality', 0)
            flame_val = data.get('flame_val', 4095) # Default Safe
            dht22_temp = data.get('dht22_temp', 0)
            humidity = data.get('humidity', 0)
            
            # 3. Predict status
            ml_result = predictor.predict(
                methane, lpg, co, air_quality, flame_val, dht22_temp, humidity
            )
            
            # 4. Save to database
            # Try to get sensor by ID sent from ESP32, or fallback to first one
            sensor_id_raw = data.get('sensor_id')
            if sensor_id_raw:
                sensor = Sensor.objects.filter(id=sensor_id_raw).first()
            else:
                sensor = Sensor.objects.first()

            if sensor:
                SensorDataLog.objects.create(
                    sensor=sensor,
                    methane=methane, lpg=lpg, co=co, air_quality=air_quality,
                    flame_val=flame_val, dht22_temp=dht22_temp, humidity=humidity,
                    status=ml_result
                )
            
            # 5. Send response to ESP32 (1=Alarm, 0=Safe)
            if ml_result != "Safe":
                print(f"⚠️ DANGER: {ml_result}")
                return HttpResponse("1") 
            else:
                return HttpResponse("0")

        except Exception as e:
            print(f"Error processing sensor data: {e}")
            return HttpResponse("0") # Default Safe on error
            
    return HttpResponse("0", status=405)

# ==========================================
#  WEB DASHBOARD VIEWS
# ==========================================

# 1. The Main Page Load
def dashboard(request):
    # This renders the HTML file initially
    return render(request, 'sensors/dashboard.html')

#The Live Data API (JavaScript calls this every 2 seconds)
def get_live_data(request):
    # Get Map Data (Active Sensors + Current Status)
    active_sensors = Sensor.objects.filter(is_active=True)
    map_data = []
    
    for sensor in active_sensors:
        last_log = sensor.readings.order_by('-timestamp').first()
        current_status = last_log.status if last_log else "Safe"
        
        map_data.append({
            'name': sensor.name,
            'lat': sensor.latitude,
            'lng': sensor.longitude,
            'status': current_status,
            'owner': sensor.owner.user.username if sensor.owner else "Unknown"
        })

    #Get Table Data (Recent History)
    recent_logs = SensorDataLog.objects.all().order_by('-timestamp')[:10]
    table_data = []
    
    for log in recent_logs:
        table_data.append({
            'timestamp': log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'sensor': log.sensor.name,
            'status': log.status,
            'temp': log.dht22_temp,
            'smoke': log.air_quality
        })

    # Return both as JSON
    return JsonResponse({
        'map_data': map_data,
        'table_data': table_data
    })