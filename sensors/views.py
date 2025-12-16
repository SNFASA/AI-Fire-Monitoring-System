from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import json
from .models import Sensor, SensorDataLog, UserProfile, Maintenance, Report, FireStation, Address, Houselayout
from ml_engine.predictor import FirePredictor
from django.core.serializers.json import DjangoJSONEncoder
from .forms import SignUpForm, UserUpdateForm, ProfileUpdateForm, AddressUpdateForm, HouseLayoutForm, SensorPlacementForm
import leafmap.maplibregl as leafmap
import math

# Init brain once
predictor = FirePredictor()

# ==========================================
#  AUTHENTICATION VIEWS (Done)
# ==========================================

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully!')
        return redirect('login')
    
    # Optional: Handle GET request if someone types /logout/ manually
    # You can either allow it (less secure) or redirect them back
    return redirect('home')
#============================
# REGISTER VIEW (Done)
#============================
def register(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            
            user = form.save(commit=False)
            user.first_name = form.cleaned_data.get('first_name')
            user.last_name = form.cleaned_data.get('last_name')
            user.email = form.cleaned_data.get('email')
            user.save()

            messages.success(request, f'Account created for {user.username}!')
            return redirect('login')
        else:
            messages.error(request, 'Registration failed. Please check errors.')
    else:
        form = SignUpForm()
    
    return render(request, 'sensors/register.html', {'form': form})

# ==========================================
#  API VIEWS FOR ESP32 DEVICE
# ==========================================
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
    if not request.user.is_authenticated:
        return redirect('login')
    
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile.objects.create(user=request.user)
    
    sensors = Sensor.objects.filter(owner=user_profile) if user_profile.role == 'public' else Sensor.objects.all()
    
    context = {
        'sensors_count': sensors.count(),
        'sensors': sensors,
        'maintenance_pending': Maintenance.objects.filter(status='Pending').count(),
        'maintenance_items': Maintenance.objects.all().order_by('-timestamp'),
        'reports_count': Report.objects.count(),
        'recent_reports': Report.objects.all().order_by('-timestamp'),
        'stations_count': FireStation.objects.count(),
    }
    
    return render(request, 'sensors/dashboard.html', context)
#=========================================  
#The Live Data API (JavaScript calls this every 2 seconds)
#=========================================
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

# ==========================================
# USER PROFILE VIEWS (Done)
# ==========================================
@login_required(login_url='login')
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    current_address = user_profile.address

    if request.method == 'POST':
        print("\n---- DEBUG START ----")
        print("FILES Data:", request.FILES) 

        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        a_form = AddressUpdateForm(request.POST, instance=user_profile.address)

        if u_form.is_valid() and p_form.is_valid() and a_form.is_valid():
            print("Forms are valid. Saving...")
            u_form.save()
            profile_instance = p_form.save()
            
            print(f"NEW Saved Image URL: {profile_instance.profile_picture}")
            address_instance = a_form.save()
            if not user_profile.address:
                user_profile.address = address_instance
                user_profile.save()

            print("---- DEBUG END (SUCCESS) ----\n")
            messages.success(request, 'Your Profile updated successfully!')
            return redirect('profile')

        else:
            print("\n!!! FORM VALIDATION FAILED !!!")
            print("Profile Errors:", p_form.errors)
            messages.error(request, 'Please correct the error below.')

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=user_profile)
        a_form = AddressUpdateForm(instance=current_address)

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'a_form': a_form,
        'user_profile': user_profile,
    }
    
    return render(request, 'sensors/profile.html', context)
# ==========================================
# CHANGE PASSWORD VIEW (Done)
# ==========================================

@login_required(login_url='login')
def change_password(request):
    """Change password view"""
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        # Validation
        if not all([old_password, new_password, confirm_password]):
            messages.error(request, '❌ All fields are required.')
            return render(request, 'sensors/change_password.html')
        
        if not request.user.check_password(old_password):
            messages.error(request, '❌ Current password is incorrect.')
            return render(request, 'sensors/change_password.html')
        
        if new_password != confirm_password:
            messages.error(request, '❌ New passwords do not match.')
            return render(request, 'sensors/change_password.html')
        
        if len(new_password) < 8:
            messages.error(request, '❌ Password must be at least 8 characters long.')
            return render(request, 'sensors/change_password.html')
        
        if new_password == old_password:
            messages.error(request, '❌ New password cannot be the same as current password.')
            return render(request, 'sensors/change_password.html')
        
        try:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, '✅ Password changed successfully! Please log in again.')
            return redirect('login')
        except Exception as e:
            messages.error(request, f'❌ Error changing password: {str(e)}')
            return render(request, 'sensors/change_password.html')
    
    return render(request, 'sensors/change_password.html')

# ==========================================
# MAINTENANCE VIEWS
# ==========================================

@login_required(login_url='login')
def maintenance(request):
    """List all maintenance records"""
    maintenance_items = Maintenance.objects.all().order_by('-timestamp')
    
    context = {
        'maintenance_items': maintenance_items,
    }
    return render(request, 'sensors/maintenance.html', context)

@login_required(login_url='login')
def maintenance_detail(request, maintenance_id):
    """Maintenance detail view with picture upload"""
    try:
        maintenance = get_object_or_404(Maintenance, id=maintenance_id)
        
        if request.method == 'POST':
            # Handle picture upload
            if 'picture' in request.FILES:
                try:
                    # Delete old picture if exists
                    if maintenance.picture:
                        maintenance.picture.delete()
                    
                    maintenance.picture = request.FILES['picture']
                    maintenance.save()
                    messages.success(request, '✅ Maintenance picture uploaded successfully!')
                except Exception as e:
                    messages.error(request, f'❌ Error uploading picture: {str(e)}')
                return redirect('maintenance_detail', maintenance_id=maintenance.id)
        
        context = {
            'maintenance': maintenance,
        }
        return render(request, 'sensors/maintenance_detail.html', context)
    except Exception as e:
        messages.error(request, f'❌ Error loading maintenance record: {str(e)}')
        return redirect('maintenance')

# ==========================================
# REPORTS VIEWS
# ==========================================

@login_required(login_url='login')
def reports(request):
    """List all fire reports"""
    reports_list = Report.objects.all().order_by('-timestamp')
    
    context = {
        'reports': reports_list,
    }
    return render(request, 'sensors/reports.html', context)

@login_required(login_url='login')
def report_detail(request, report_id):
    """Report detail view"""
    report = get_object_or_404(Report, id=report_id)
    
    context = {
        'report': report,
    }
    return render(request, 'sensors/report_detail.html', context)

@login_required(login_url='login')
def create_report(request):
    """Create new fire report"""
    stations = FireStation.objects.all()
    addresses = Address.objects.all()
    
    if request.method == 'POST':
        fire_type = request.POST.get('fire_type', '').strip()
        cause = request.POST.get('cause', '').strip()
        station_id = request.POST.get('station', '')
        address_id = request.POST.get('address', '')
        
        # Validation
        if not fire_type or not cause or not station_id:
            messages.error(request, '❌ Fire type, cause, and station are required.')
            context = {'stations': stations, 'addresses': addresses}
            return render(request, 'sensors/create_report.html', context)
        
        try:
            station = FireStation.objects.get(id=station_id)
            address = Address.objects.get(id=address_id) if address_id else None
            
            report = Report.objects.create(
                fire_type=fire_type,
                cause=cause,
                station=station,
                address=address,
                in_charge=request.user,
            )
            
            # Handle picture upload
            if 'picture' in request.FILES:
                try:
                    report.picture = request.FILES['picture']
                    report.save()
                except Exception as e:
                    messages.warning(request, f'⚠️ Report created but picture upload failed: {str(e)}')
            
            messages.success(request, '✅ Fire report created successfully!')
            return redirect('report_detail', report_id=report.id)
        
        except FireStation.DoesNotExist:
            messages.error(request, '❌ Selected fire station does not exist.')
        except Exception as e:
            messages.error(request, f'❌ Error creating report: {str(e)}')
    
    context = {
        'stations': stations,
        'addresses': addresses,
    }
    return render(request, 'sensors/create_report.html', context)

#========================================
# Upload House Layout
#========================================
@login_required(login_url='login')
def upload_layout(request):
    existing_layout = Houselayout.objects.filter(user=request.user).first()
    if request.method == "POST":
        form = HouseLayoutForm(request.POST, request.FILES, instance=existing_layout)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.user = request.user
            layout.save()
            return redirect('maps')
    else:
        form = HouseLayoutForm(instance=existing_layout)
        print("\n!!! FORM VALIDATION FAILED !!!")
        print("Profile Errors:", form.errors)
        messages.error(request, 'Please correct the error below.')
    return render(request, 'sensors/upload_layout.html', {'form': form})
#==========================================
# ADD SENSOR 
#==========================================
@login_required
def add_sensor(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            sensor_name = data.get('name')
            
            if not sensor_name:
                return JsonResponse({'success': False, 'error': 'Name is required'})

            user_profile = request.user.userprofile
            user_layout = Houselayout.objects.filter(user=request.user).first()

            # Create the sensor
            new_sensor = Sensor.objects.create(
                owner=user_profile,
                name=sensor_name,
                layout=user_layout,
                x_position=5.0,  # Default to top-left
                y_position=5.0,
                is_active=True
            )
            
            return JsonResponse({
                'success': True, 
                'sensor_id': new_sensor.id, 
                'name': new_sensor.name
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})
# ==========================================
# API: Add New Sensor
# ==========================================
@login_required
def add_sensor(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            sensor_name = data.get('name')
            
            if not sensor_name:
                return JsonResponse({'success': False, 'error': 'Name is required'})

            user_profile = request.user.userprofile
            user_layout = Houselayout.objects.filter(user=request.user).first()

            # Create the sensor
            new_sensor = Sensor.objects.create(
                owner=user_profile,
                name=sensor_name,
                layout=user_layout,
                x_position=5.0,  # Default: Top-left corner (5%)
                y_position=5.0,  # Default: Top-left corner (5%)
                is_active=True
            )
            
            return JsonResponse({
                'success': True, 
                'sensor_id': new_sensor.id, 
                'name': new_sensor.name
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})
# ==========================================
# API: Save Sensor Position (User only)
# ==========================================
@csrf_exempt
@login_required
def update_sensor_position(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            sensor = Sensor.objects.get(id=data['sensor_id'], owner__user=request.user)
            sensor.x_position = data['x']
            sensor.y_position = data['y']
            sensor.save()
            return JsonResponse({'success': True})
        except Sensor.DoesNotExist:
            return JsonResponse({'success': False})
    return JsonResponse({'success': False})
# ==========================================
# THE MAIN MAPS PAGE 
# ==========================================
@login_required(login_url='login')
def maps(request):
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        return render(request, 'sensors/maps.html', {'role': 'unknown'})

    context = {
        'role': user_profile.role,
        'user_profile': user_profile,
        'sensors': Sensor.objects.all(),
    }
    
    # --- FIRE STATION LOGIC ---
    try:
        station = FireStation.objects.first()
        
        # Default fallback values
        lat = 1.8548
        lng = 103.0848
        radius_km = 3.0
        name = "HQ (Default)"

        if station and station.address:
            # 1. Get Coordinates
            if station.address.latitude is not None and station.address.longitude is not None:
                lat = station.address.latitude
                lng = station.address.longitude # CHANGED to 'lng'
            
            # 2. Get Name
            name = station.name

            # 3. Calculate Radius
            if station.cover_area_sqm:
                import math
                # formula: radius = sqrt(area / pi) / 1000 (for km)
                radius_meters = math.sqrt(station.cover_area_sqm / math.pi)
                radius_km = radius_meters / 1000

        # Pass to context with CORRECT keys
        context['station_lat'] = lat
        context['station_lng'] = lng  # FIXED: Matches template variable
        context['station_radius'] = radius_km
        context['station_name'] = name

    except Exception as e:
        print(f"Map Error: {e}")
        # Fallback if DB crashes
        context['station_lat'] = 1.8548
        context['station_lng'] = 103.0848
        context['station_radius'] = 3.0
        context['station_name'] = "HQ (Error)"

    # PUBLIC USER LOGIC
    if user_profile.role == 'public':
        layout = Houselayout.objects.filter(user=request.user).first()
        sensors = user_profile.sensors.all()
        context.update({'layout': layout, 'sensors': sensors})

    return render(request, 'sensors/maps.html', context)

# ==========================================
#  API: Firefighter 3D Map Data
# ==========================================
@login_required
def firefighter_map_data(request):
    # Only Firefighters
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    data = []
    users = UserProfile.objects.filter(role='public').select_related('address')

    for profile in users:
        if profile.address and profile.address.latitude and profile.address.longitude:
            sensors = profile.sensors.all()
            status = "Safe"
            
            # Determine status based on highest threat
            for s in sensors:
                last = s.readings.last()
                if last:
                    if last.status == 'Fire':
                        status = 'Fire'
                        break
                    elif last.status == 'GasLeak' and status != 'Fire':
                        status = 'GasLeak'

            data.append({
                'id': profile.user.id, # We use User ID to fetch layout later
                'owner': profile.user.username,
                'lat': profile.address.latitude,
                'lng': profile.address.longitude,
                'status': status
            })

    return JsonResponse({'houses': data})

# ==========================================
# API: Get Specific Victim Layout
# ==========================================
@login_required
def get_victim_layout(request, user_id):
    # Security: Only firefighters can see other people's layouts
    if request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        layout = Houselayout.objects.get(user_id=user_id)
        sensors = Sensor.objects.filter(owner__user_id=user_id)
        
        sensor_data = []
        for s in sensors:
            reading = s.readings.last()
            status = reading.status if reading else 'Safe'
            sensor_data.append({
                'name': s.name,
                'x': s.x_position,
                'y': s.y_position,
                'status': status
            })

        return JsonResponse({
            'success': True,
            'image_url': layout.image.url,
            'owner': layout.user.username,
            'sensors': sensor_data
        })
    except Houselayout.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No layout found for this user'})



