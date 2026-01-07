from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import json
from .models import Sensor, SensorDataLog, UserProfile, Maintenance, Report, FireStation, Address, Houselayout, ReportImage, DutyAssignment
from ml_engine.predictor import FirePredictor
from django.core.serializers.json import DjangoJSONEncoder
from .forms import SignUpForm, UserUpdateForm, ProfileUpdateForm, AddressUpdateForm, HouseLayoutForm, SensorPlacementForm
import leafmap.maplibregl as leafmap
import math
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .logger import get_logs, add_log
# Init AI Engine
predictor = FirePredictor()
system_logs = []
# ==========================================
# 1. HELPER FUNCTION (MOVED TO TOP)
# ==========================================
def get_sensor_status(sensor):
    """
    Returns: 'Fire', 'Gas Leak', 'Safe', or 'Offline'
    """
    # 1. Check for recent data
    last_log = sensor.readings.order_by('-timestamp').first()
    
    if not last_log:
        return "Offline" 
        
    # 2. Check time difference (5 minutes threshold)
    time_diff = timezone.now() - last_log.timestamp
    if time_diff > timedelta(minutes=5):
        return "Offline"
        
    # 3. Return actual AI status
    # Normalize 'GasLeak' to 'Gas Leak' for consistency
    status = last_log.status
    if status == 'GasLeak': 
        return 'Gas Leak'
    return status
def get_live_logs(request):
    # This fetches data from the shared memory
    return JsonResponse({'logs': get_logs()})
def test_log(request):
    add_log("\n[TEST] This is a test log entry to verify the dashboard.\n")
    return JsonResponse({'status': 'Log added'})
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
    predictor = FirePredictor()
    model_name = predictor.get_active_model_info()
    
    context = {
        'sensors_count': sensors.count(),
        'sensors': sensors,
        'ml_model_name': model_name,
        'maintenance_pending': Maintenance.objects.filter(status='Pending').count(),
        'maintenance_items': Maintenance.objects.all().order_by('-timestamp'),
        'reports_count': Report.objects.count(),
        'recent_reports': Report.objects.all().order_by('-timestamp'),
        'stations_count': FireStation.objects.count(),
    }
    
    return render(request, 'sensors/dashboard.html', context)
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
#==========================================
# DUTY VIEW
#==========================================
@login_required(login_url='login')
@xframe_options_sameorigin
def duty(request):
    user_profile = UserProfile.objects.get(user=request.user)
    my_schedule = DutyAssignment.objects.filter(
        firefighter=user_profile,
        is_active=True,
        start_time__gte=timezone.now()
    ).order_by('start_time')
    
    context = {
        'my_schedule': my_schedule,
    }
    return render(request, 'sensors/duty_popup.html', context)
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

@login_required(login_url='login')
def create_maintenance(request):
    """Create new maintenance record"""
    return render(request, 'sensors/create_maintenance.html')

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
    """
    View for Firefighters to:
    1. See the auto-generated data
    2. Upload photos (Multi-pic)
    3. Confirm the report details
    """
    report = get_object_or_404(Report, id=report_id)
    stations = FireStation.objects.all()

    # Security: Ensure only firefighters can edit
    is_firefighter = hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'firefighter'

    if request.method == 'POST' and is_firefighter:
        try:
            # 1. Update Basic Info
            report.fire_type = request.POST.get('fire_type')
            report.cause = request.POST.get('cause')
            report.description = request.POST.get('description')
            report.status = request.POST.get('status') # E.g., change 'System Detected' to 'Confirmed'
            
            # Update Station
            station_id = request.POST.get('station')
            if station_id:
                report.station = FireStation.objects.get(id=station_id)
            
            # Set In Charge
            report.in_charge = request.user
            report.save()

            # 2. Handle Multiple Images
            images = request.FILES.getlist('images') # 'images' comes from <input type="file" multiple>
            for image_file in images:
                ReportImage.objects.create(report=report, image=image_file)

            messages.success(request, 'Report updated and confirmed successfully!')
            return redirect('reports')

        except Exception as e:
            messages.error(request, f"Error updating report: {e}")

    context = {
        'report': report,
        'stations': stations,
        'is_firefighter': is_firefighter
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
# ==========================================
# THE MAIN MAPS PAGE 
# ==========================================
@login_required(login_url='login')
def maps(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        return render(request, 'sensors/maps.html', {'role': 'unknown'})

    context = {
        'role': user_profile.role,
        'user_profile': user_profile,
        # Only load sensors for public users to improve performance/security
        'sensors': user_profile.sensors.all() if user_profile.role == 'public' else [], 
    }

    # --- FIRE STATION LOGIC (FIXED) ---
    if user_profile.role == 'firefighter':
        try:
            # 1. PRIORITY: Get the station assigned to this specific firefighter
            station = user_profile.station
            
            # 2. FALLBACK: If they haven't been assigned a station, use the first one
            if not station:
                station = FireStation.objects.first()

            # Default values (Center of Batu Pahat/Johor as fallback)
            lat = 1.8548
            lng = 103.0848
            radius_km = 3.0
            name = "HQ (Unassigned)"

            if station:
                # Get Name
                name = station.name

                # Get Coordinates (Data Validation)
                # We check "is not None" because 0.0 is a valid coordinate, but None is not.
                if station.address and station.address.latitude is not None and station.address.longitude is not None:
                    lat = float(station.address.latitude)
                    lng = float(station.address.longitude)
                
                # Calculate Radius
                if station.cover_area_sqm:
                    import math
                    # Formula: radius = sqrt(area / pi) / 1000 (to get km)
                    radius_meters = math.sqrt(station.cover_area_sqm / math.pi)
                    radius_km = radius_meters / 1000

            # Pass to context
            context['station_lat'] = lat
            context['station_lng'] = lng
            context['station_radius'] = radius_km
            context['station_name'] = name

        except Exception as e:
            print(f"Map Error: {e}")
            # Emergency Fallback
            context['station_lat'] = 1.8548
            context['station_lng'] = 103.0848
            context['station_radius'] = 3.0
            context['station_name'] = "System Error"

    # --- PUBLIC USER LOGIC ---
    if user_profile.role == 'public':
        layout = Houselayout.objects.filter(user=request.user).first()
        context['layout'] = layout

    return render(request, 'sensors/maps.html', context)
# ==========================================
#  API: LIVE DATA FOR PUBLIC USER
# ==========================================
@login_required
def get_live_data(request):
    """ Called by JS to update sensor colors/text """
    try:
        # FIX: Order by ID to match HTML list order
        user_sensors = Sensor.objects.filter(owner=request.user.userprofile).order_by('id')
    except:
        return JsonResponse({'sensors': []})

    sensor_data = []
    for s in user_sensors:
        status = get_sensor_status(s)
        sensor_data.append({
            'id': s.id,
            'name': s.name,
            'status': status,
            'x': s.x_position,
            'y': s.y_position
        })

    return JsonResponse({'sensors': sensor_data})
# ==========================================
#  API: Firefighter 3D Map Data
# ==========================================
@login_required
def firefighter_map_data(request):
    """ Returns all houses and their aggregated status """
    # Security check
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    data = []
    # Get all public users with an address
    users = UserProfile.objects.filter(role='public').select_related('address')

    for profile in users:
        if profile.address and profile.address.latitude:
            sensors = profile.sensors.all()
            
            # --- Aggregation Logic ---
            house_status = "Safe"
            has_offline = False
            
            for s in sensors:
                s_status = get_sensor_status(s) # Helper handles 'Offline' logic
                
                if s_status == 'Fire':
                    house_status = 'Fire'
                    break # Fire takes priority
                elif s_status == 'Gas Leak' and house_status != 'Fire':
                    house_status = 'Gas Leak'
                elif s_status == 'Offline':
                    has_offline = True

            # Logic: If safe but has offline sensors, mark house as Offline (optional)
            if house_status == "Safe" and has_offline and sensors.exists():
                house_status = "Offline"

            data.append({
                'id': profile.user.id,
                'owner': profile.user.username,
                'lat': profile.address.latitude,
                'lng': profile.address.longitude,
                'status': house_status
            })

    return JsonResponse({'houses': data})

# ==========================================
# API: Get Specific Victim Layout
# ==========================================
@login_required
def get_victim_layout(request, user_id):
    """ Returns sensors for a specific house (Firefighter View) """
    if request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        layout = Houselayout.objects.get(user_id=user_id)
        # FIX: Order by ID to prevent dots shuffling in the popup
        sensors = Sensor.objects.filter(owner__user_id=user_id).order_by('id')
        
        sensor_data = []
        for s in sensors:
            status = get_sensor_status(s)
            
            sensor_data.append({
                'id': s.id,       # CRITICAL: JS needs this ID to sort dots
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
        return JsonResponse({'success': False, 'error': 'No layout found'})
    
# ==========================================
# ESP32 DATA INGESTION
# ==========================================
# In views.py

@csrf_exempt
def receive_sensor_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # 1. Parse Data
            methane = data.get('methane', 0) 
            lpg = data.get('lpg', 0)
            co = data.get('co', 0)
            air_quality = data.get('air_quality', 0)
            flame_val = data.get('flame_val', 4095)
            dht22_temp = data.get('dht22_temp', 0)
            humidity = data.get('humidity', 0)
            
            # --- LOGGING START (This makes it show on Dashboard) ---
            import datetime
            current_time = datetime.datetime.now().strftime('%H:%M:%S')
            
            # Create the log string
            log_msg = (
                f"\n[🔮 PREDICTOR LOG] {current_time}\n"
                f"   ├─ Inputs: Met={methane}, LPG={lpg}, CO={co}, AQ={air_quality}\n"
                f"   └─ Inputs: Flame={flame_val}, Temp={dht22_temp}, Hum={humidity}\n"
            )
            
            # Send to Console AND Dashboard
            print(log_msg) 
            add_log(log_msg) 
            # --- LOGGING END ---

            # 2. AI Prediction
            ml_result = predictor.predict(
                methane, lpg, co, air_quality, flame_val, dht22_temp, humidity
            )
            
            # Log the result
            add_log(f"   ℹ️  AI Status: [{ml_result}]\n")

            # 3. Find Sensor
            sensor_id_raw = data.get('sensor_id')
            sensor = Sensor.objects.filter(id=sensor_id_raw).first() if sensor_id_raw else None

            if sensor:
                # 4. Save to Database
                SensorDataLog.objects.create(
                    sensor=sensor,
                    methane=methane, lpg=lpg, co=co, air_quality=air_quality,
                    flame_val=flame_val, dht22_temp=dht22_temp, humidity=humidity,
                    status=ml_result
                )

                # 5. Report Logic (Only if Fire)
                if ml_result == "Fire" and sensor.owner.address:
                    user_address = sensor.owner.address
                    
                    existing_report = Report.objects.filter(
                        address=user_address,
                        status__in=['System Detected', 'Confirmed']
                    ).first()

                    if existing_report:
                        existing_report.save() # Update timestamp
                    else:
                        Report.objects.create(
                            status='System Detected',
                            address=user_address,
                            trigger_sensor=sensor,
                            trigger_temperature=dht22_temp,
                            trigger_gas_level=max(methane, lpg, co, air_quality),
                            description=f"Automated Alert: Fire detected by sensor '{sensor.name}'."
                        )
            
            # 6. Response
            return HttpResponse("1" if ml_result != "Safe" else "0")

        except Exception as e:
            error_msg = f"   ❌ Error processing data: {e}\n"
            print(error_msg)
            add_log(error_msg) # Log errors too
            return HttpResponse("0")
            
    return HttpResponse("0", status=405)
@csrf_exempt
@login_required
def add_sensor(request):
    """ Adds a new sensor via the Public Dashboard """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            sensor_name = data.get('name')
            
            if not sensor_name:
                return JsonResponse({'success': False, 'error': 'Name is required'})

            user_profile = request.user.userprofile
            user_layout = Houselayout.objects.filter(user=request.user).first()

            new_sensor = Sensor.objects.create(
                owner=user_profile,
                name=sensor_name,
                layout=user_layout,
                x_position=5.0, 
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
            
    return JsonResponse({'success': False, 'error': 'Invalid method'})

@csrf_exempt
@login_required
def update_sensor_position(request):
    """ Saves drag-and-drop coordinates """
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            # Ensure user owns the sensor
            sensor = Sensor.objects.get(id=data['sensor_id'], owner__user=request.user)
            sensor.x_position = data['x']
            sensor.y_position = data['y']
            sensor.save()
            return JsonResponse({'success': True})
        except Sensor.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Sensor not found or unauthorized'})
    return JsonResponse({'success': False})