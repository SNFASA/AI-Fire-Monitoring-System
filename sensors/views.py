from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import json
from .models import Sensor, SensorDataLog, UserProfile, Maintenance,MaintenanceImage, Report, FireStation, Address, Houselayout, ReportImage, DutyAssignment
from ml_engine.predictor import FirePredictor
from django.core.serializers.json import DjangoJSONEncoder
from .forms import SignUpForm, UserUpdateForm, ProfileUpdateForm, AddressUpdateForm, HouseLayoutForm, SensorPlacementForm, MaintenanceForm
import leafmap.maplibregl as leafmap
import math
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .logger import get_logs, add_log
from django.db.models import Q
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
# 1. The Main Page 
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
    try:
        user_role = request.user.userprofile.role
    except AttributeError:
        user_role = 'public'
    if user_role == 'public':
        maintenances = Maintenance.objects.all().order_by('-scheduled_date')

    else:
        maintenances = Maintenance.objects.filter(
            Q(status='Pending') | Q(in_charge=request.user)
        ).order_by('-scheduled_date')
    maintenance_images = MaintenanceImage.objects.all()
    context = {
        'maintenance_items': maintenances, 
        'maintenance_images': maintenance_images,
        'user_role': user_role
    }
    return render(request, 'sensors/maintenance.html', context)
@login_required(login_url='login')
def maintenance_detail(request, maintenance_id):
    try:
        maintenance = get_object_or_404(Maintenance, id=maintenance_id)
        UserProfile.objects.get(user=request.user)  # Ensure profile exists
        if request.method == 'POST':
            if 'picture' in request.FILES:
                try:
                    image_file = request.FILES['picture']
                    MaintenanceImage.objects.create(
                        maintenance=maintenance,
                        image=image_file
                    )
                    messages.success(request, '✅ Evidence picture uploaded successfully!')
                except Exception as e:
                    messages.error(request, f'❌ Error uploading picture: {str(e)}')
                return redirect('maintenance_detail', maintenance_id=maintenance.id)
        
        context = {
            'maintenance': maintenance,\
        }
        return render(request, 'sensors/maintenance_detail.html', context)
        
    except Exception as e:
        messages.error(request, f'❌ Error loading maintenance record: {str(e)}')
        return redirect('maintenance')
# In sensors/views.py
@login_required(login_url='login')
def create_maintenance(request):
    if request.method == 'POST':
        form = MaintenanceForm(request.POST, request.FILES)
        
        if form.is_valid():
            maintenance_instance = form.save(commit=False)
            maintenance_instance.save() 
            images = request.FILES.getlist('images') 
            
            for img in images:
                MaintenanceImage.objects.create(
                    maintenance=maintenance_instance,
                    image=img                         
                )
            
            return redirect('maintenance') 
            
        else:
            print("❌ Form Errors:", form.errors)
            
    else:
        form = MaintenanceForm()
    
    return render(request, 'sensors/maintenance_create.html', {'form': form})
@login_required(login_url='login')
def edit_maintenance(request, maintenance_id):
    maintenance_task = get_object_or_404(Maintenance, id=maintenance_id)
    user_role = 'public' 
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            user_role = profile.role
        except UserProfile.DoesNotExist:
            user_role = 'public'
    if user_role == 'public' and maintenance_task.status != 'pending':
        messages.error(request, "You cannot edit this request because it is already being processed.")
        return redirect('maintenance_detail', maintenance_id=maintenance_task.id)

    if request.method == 'POST':
        if user_role == 'public':
            form = MaintenanceForm(request.POST, request.FILES, instance=maintenance_task)
            if form.is_valid():
                maintenance_instance = form.save()
                handle_images(request, maintenance_instance)
                messages.success(request, "Request updated successfully.")
                return redirect('maintenance_detail', maintenance_id=maintenance_instance.id)
        else:
            maintenance_task.status = request.POST.get('status')
            maintenance_task.actual_date = request.POST.get('actual_date')
            maintenance_task.technician_notes = request.POST.get('technician_notes')
            
            if not maintenance_task.in_charge:
                maintenance_task.in_charge = request.user
            
            maintenance_task.save()
            handle_images(request, maintenance_task)
            
            messages.success(request, "Technician report updated.")
            return redirect('maintenance_detail', maintenance_id=maintenance_task.id)
    else:
        form = MaintenanceForm(instance=maintenance_task)

    context = {
        'form': form,
        'maintenance': maintenance_task,
        'user_role': user_role,
    }
    return render(request, 'sensors/maintenance_edit.html', context)

# Helper function to avoid duplicate code
def handle_images(request, maintenance_instance):
    images = request.FILES.getlist('images')
    for img in images:
        MaintenanceImage.objects.create(
            maintenance=maintenance_instance,
            image=img
        )
    
    # 2. Delete Selected Images
    delete_images_ids = request.POST.getlist('delete_images')
    if delete_images_ids:
        MaintenanceImage.objects.filter(
            id__in=delete_images_ids, 
            maintenance=maintenance_instance
        ).delete()
            
def delete_maintenance(request, maintenance_id):
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    maintenance.delete()
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
    # Allow uploading NEW layouts (removed instance=existing)
    if request.method == "POST":
        form = HouseLayoutForm(request.POST, request.FILES)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.user = request.user
            layout.save()
            messages.success(request, f'Floor plan "{layout.name}" added successfully!')
            return redirect('maps')
    else:
        form = HouseLayoutForm()

    # Get ALL layouts to show the list
    existing_layouts = Houselayout.objects.filter(user=request.user).order_by('-timestamp')
    
    context = {
        'form': form,
        'existing_layouts': existing_layouts
    }
    return render(request, 'sensors/upload_layout.html', context)
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
    }

    # --- PUBLIC USER LOGIC ---
    if user_profile.role == 'public':
        # Get ALL layouts
        user_layouts = Houselayout.objects.filter(user=request.user).order_by('id')
        
        # Determine Current Layout
        selected_layout_id = request.GET.get('layout_id')
        current_layout = None
        
        if user_layouts.exists():
            if selected_layout_id:
                current_layout = user_layouts.filter(id=selected_layout_id).first()
            if not current_layout:
                current_layout = user_layouts.first()

        context['layouts'] = user_layouts
        context['current_layout'] = current_layout
        
        # Filter Sensors for CURRENT Layout only
        if current_layout:
            context['sensors'] = Sensor.objects.filter(owner=user_profile, layout=current_layout)
        else:
            context['sensors'] = []

    # --- FIREFIGHTER LOGIC ---
    elif user_profile.role == 'firefighter':
        try:
            station = user_profile.station
            if not station: station = FireStation.objects.first()

            lat, lng = 1.8548, 103.0848
            radius_km = 3.0
            name = "HQ"

            if station:
                name = station.name
                if station.address and station.address.latitude:
                    lat = float(station.address.latitude)
                    lng = float(station.address.longitude)
                if station.cover_area_sqm:
                    import math
                    radius_km = math.sqrt(station.cover_area_sqm / math.pi) / 1000

            context['station_lat'] = lat
            context['station_lng'] = lng
            context['station_radius'] = radius_km
            context['station_name'] = name

        except Exception as e:
            print(f"Map Error: {e}")

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
    if request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Get ALL layouts for victim
    layouts = Houselayout.objects.filter(user_id=user_id)
    
    if not layouts.exists():
        return JsonResponse({'success': False, 'error': 'No layouts found'})

    results = []
    for layout in layouts:
        # Helper to get status
        from .views import get_sensor_status # Import helper if needed locally or move to top
        sensors = Sensor.objects.filter(layout=layout)
        
        sensor_data = []
        for s in sensors:
            status = get_sensor_status(s)
            sensor_data.append({
                'id': s.id, 'name': s.name, 
                'x': s.x_position, 'y': s.y_position, 
                'status': status
            })
        
        results.append({
            'layout_id': layout.id,
            'layout_name': layout.name,
            'image_url': layout.image.url,
            'sensors': sensor_data
        })

    return JsonResponse({
        'success': True,
        'layouts': results # Returns list
    })
# ==========================================
# ESP32 DATA INGESTION (sensor)
# ==========================================

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
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            sensor_name = data.get('name')
            layout_id = data.get('layout_id') # New Field
            
            if not sensor_name: return JsonResponse({'success': False, 'error': 'Name required'})
            if not layout_id: return JsonResponse({'success': False, 'error': 'Layout ID required'})

            # Verify ownership
            layout = Houselayout.objects.get(id=layout_id, user=request.user)

            new_sensor = Sensor.objects.create(
                owner=request.user.userprofile,
                name=sensor_name,
                layout=layout, # Link to floor
                x_position=50.0, 
                y_position=50.0,
                is_active=True
            )
            return JsonResponse({'success': True, 'sensor_id': new_sensor.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid method'})


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
            return JsonResponse({'success': False, 'error': 'Error'})
    return JsonResponse({'success': False})

@login_required
def delete_sensor(request, sensor_id):
    if request.method == "POST":
        try:
            # Ensure user owns the sensor
            sensor = Sensor.objects.get(id=sensor_id, owner__user=request.user, maintenance__status__in=['completed_with_damages'])
            sensor.delete()
            return redirect('dashboard')
        except Sensor.DoesNotExist:
            messages.error(request, '❌ Sensor not found or unauthorized.')
            return redirect('dashboard')
    messages.error(request, '❌ Invalid request method.')
    return redirect('dashboard')

# sensors/views.py

from django.views.decorators.http import require_POST

# ==========================================
# NEW: API for Public Dashboard Real-time Data
# ==========================================
@login_required
def get_dashboard_sensor_data(request):
    """
    Returns JSON data for the public dashboard table.
    """
    try:
        # 1. Get Profile
        user_profile = UserProfile.objects.get(user=request.user)

        # 2. MATCH DASHBOARD LOGIC:
        # If public, show only their sensors. If Admin/Other, show ALL sensors.
        if user_profile.role == 'public':
            sensors = Sensor.objects.filter(owner=user_profile).order_by('id')
        else:
            sensors = Sensor.objects.all().order_by('id')
        
        data = []
        for sensor in sensors:
            last_log = sensor.readings.order_by('-timestamp').first()
            
            if last_log:
                temp = f"{last_log.dht22_temp:.1f}°C"
                hum = f"{last_log.humidity:.1f}%"
                status = last_log.status
            else:
                temp = "N/A"
                hum = "N/A"
                
            data.append({
                'id': sensor.id,
                'temp': temp,
                'hum': hum,
                'status': status
            })
            
        return JsonResponse({'sensors': data})
    except Exception as e:
        print(f"API Error: {e}") # Debugging
        return JsonResponse({'error': str(e)}, status=500)

# ==========================================
# NEW: AJAX Delete View (No Reload)
# ==========================================
@login_required
@require_POST # Security: Only allow POST requests
def delete_sensor_ajax(request, sensor_id):
    """
    Deletes a sensor and returns JSON so the page doesn't reload.
    """
    try:
        # 1. Find the sensor (ensure the logged-in user actually owns it)
        sensor = Sensor.objects.get(id=sensor_id, owner__user=request.user)
        
        # 2. Delete it
        sensor_name = sensor.name
        sensor.delete()
        
        return JsonResponse({'success': True, 'message': f'Sensor {sensor_name} deleted successfully'})
        
    except Sensor.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Sensor not found or unauthorized'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
@require_POST
def delete_layout_ajax(request, layout_id):
    try:
        # 1. Find layout (ensure ownership)
        layout = Houselayout.objects.get(id=layout_id, user=request.user)
        layout_name = layout.name
        
        # 2. Delete
        layout.delete()
        
        return JsonResponse({'success': True, 'message': f'Layout "{layout_name}" deleted successfully'})
    
    except Houselayout.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Layout not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
@require_POST
def edit_layout_ajax(request):
    """
    Updates a layout (Name and/or Image) via AJAX Modal.
    """
    layout_id = request.POST.get('layout_id')
    
    try:
        # Ensure the layout belongs to the logged-in user
        layout = Houselayout.objects.get(id=layout_id, user=request.user)
        
        # 1. Update Name
        new_name = request.POST.get('name')
        if new_name:
            layout.name = new_name

        # 2. Update Image (only if a new file is uploaded)
        if 'image' in request.FILES:
            layout.image = request.FILES['image']

        layout.save()
        
        return JsonResponse({'success': True, 'message': 'Layout updated successfully'})

    except Houselayout.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Layout not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)