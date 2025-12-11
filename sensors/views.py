from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import json
from .models import Sensor, SensorDataLog, UserProfile, Maintenance, Report, FireStation, Address
from ml_engine.predictor import FirePredictor
from django.core.serializers.json import DjangoJSONEncoder
from .forms import SignUpForm, UserUpdateForm, ProfileUpdateForm, AddressUpdateForm

# Init brain once
predictor = FirePredictor()

# ==========================================
#  AUTHENTICATION VIEWS
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
# REGISTER VIEW
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

# ==========================================
# USER PROFILE VIEWS
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
# CHANGE PASSWORD VIEW
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