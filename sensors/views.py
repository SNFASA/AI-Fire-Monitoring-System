import json
import math
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from datetime import timedelta
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

# Local Imports
from .models import (Sensor, SensorDataLog, UserProfile, Maintenance, MaintenanceImage, 
                     Report, FireStation, Address, Houselayout, ReportImage, DutyAssignment)
from .forms import ReportUpdateForm, SignUpForm, UserUpdateForm, ProfileUpdateForm, AddressUpdateForm, HouseLayoutForm, MaintenanceForm
from ml_engine.predictor import FirePredictor
from .utils import send_sms_broadcast, haversine 
from .logger import get_logs, add_log

# Initialize AI Engine
predictor = FirePredictor()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_sensor_status(sensor):
    """ Determines if a sensor is Safe, Fire, Warning, or Offline """
    last_log = sensor.readings.order_by('-timestamp').first()
    
    # Offline Check (No data for 5 minutes)
    if not last_log: 
        return "Offline" 
    if timezone.now() - last_log.timestamp > timedelta(minutes=5): 
        return "Offline"
    
    # Return Status (Normalize 'GasLeak')
    status = last_log.status
    if status == 'GasLeak': 
        return 'Gas Leak'
    return status

def get_live_logs(request):
    """ Returns system logs for the terminal UI """
    return JsonResponse({'logs': get_logs()})

def test_log(request):
    add_log("\n[TEST] This is a test log entry.\n")
    return JsonResponse({'status': 'Log added'})

# ==========================================
# 1. SMART DISPATCH (AI + LOCATION LOGIC)
# ==========================================
@csrf_exempt
def receive_sensor_data(request):
    """
    Receives JSON from Simulator -> Runs AI -> Finds Nearest ACTIVE Station -> Sends Alerts
    """
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
            sensor_id_raw = data.get('sensor_id')

            # 2. AI Prediction
            ml_result = predictor.predict(methane, lpg, co, air_quality, flame_val, dht22_temp, humidity)
            
            # Log to Console/Dashboard
            print(f"📡 [DATA] Sensor {sensor_id_raw} | Status: {ml_result}")
            add_log(f"[DATA] Sensor {sensor_id_raw}: {ml_result}")

            sensor = Sensor.objects.filter(id=sensor_id_raw).first() if sensor_id_raw else None

            if sensor:
                # 3. Save Log to Database
                SensorDataLog.objects.create(
                    sensor=sensor, methane=methane, lpg=lpg, co=co, air_quality=air_quality,
                    flame_val=flame_val, dht22_temp=dht22_temp, humidity=humidity, status=ml_result
                )

                # 4. FIRE ALERT LOGIC
                if ml_result == "Fire" and sensor.owner.address:
                    user_address = sensor.owner.address
                    
                    # Deduplication: Don't spam if report is already active
                    active_report = Report.objects.filter(
                        address=user_address,
                        status__in=['System Detected', 'Confirmed']
                    ).first()

                    if active_report:
                        active_report.save() # Update timestamp
                        print(f"ℹ️ Alert updated for Report #{active_report.id}")
                    else:
                        # --- FIND NEAREST STATION WITH ACTIVE STAFF ---
                        stations = FireStation.objects.all()
                        station_distances = []
                        
                        # Calculate distances to all stations
                        if user_address.latitude and user_address.longitude:
                            for station in stations:
                                if station.address.latitude and station.address.longitude:
                                    dist = haversine(
                                        user_address.latitude, user_address.longitude, 
                                        station.address.latitude, station.address.longitude
                                    )
                                    station_distances.append((dist, station))
                        
                        # Sort by Nearest
                        station_distances.sort(key=lambda x: x[0])
                        
                        target_station = None
                        target_staff = []
                        now = timezone.now()

                        # Loop to find the first station that has people ON DUTY
                        for dist, station in station_distances:
                            on_duty = DutyAssignment.objects.filter(
                                firefighter__station=station,
                                start_time__lte=now,
                                end_time__gte=now,
                                is_active=True
                            ).select_related('firefighter')
                            
                            if on_duty.exists():
                                target_station = station
                                target_staff = on_duty
                                print(f"✅ Active Station Found: {station.name} ({dist:.2f}km)")
                                break
                        
                        # Fallback: If nobody is working anywhere, default to the nearest station
                        if not target_station and station_distances:
                            target_station = station_distances[0][1]
                            print(f"⚠️ No active staff found. Defaulting to nearest: {target_station.name}")

                        if target_station:
                            # 5. Create Report
                            new_report = Report.objects.create(
                                status='System Detected',
                                address=user_address,
                                trigger_sensor=sensor,
                                trigger_reading=dht22_temp,
                                trigger_gas_level= max(methane, lpg, co),
                                trigger_temperature=dht22_temp,
                                station=target_station,
                                description=f"Automated Alert: Fire at {user_address.street}."
                            )

                            # 6. SEND ALERTS
                            channel_layer = get_channel_layer()
                            payload = {
                                'type': 'fire_alert',
                                'report_id': new_report.id,
                                'address': f"{user_address.street}, {user_address.city}",
                                'owner_name': sensor.owner.user.username,
                                'owner_phone': sensor.owner.phone_number,
                                'lat': user_address.latitude,
                                'lng': user_address.longitude,
                                'timestamp': str(new_report.timestamp)
                            }
                            
                            # A. WebSocket to Station Dashboard (The Popup)
                            async_to_sync(channel_layer.group_send)(f'station_{target_station.id}', payload)
                            # B. WebSocket to Global Admins
                            async_to_sync(channel_layer.group_send)('station_all', payload)
                            
                            # C. WhatsApp to On-Duty Firefighters
                            phone_list = [d.firefighter.phone_number for d in target_staff if d.firefighter.phone_number]
                            
                            if phone_list:
                                msg = f"FIRE ALERT! Loc: {user_address.street}. Station {target_station.name} mobilized."
                                send_sms_broadcast(phone_list, msg)
                            
                            if sensor.owner.phone_number:
                                owner_msg = f"URGENT: Fire detected at your property ({user_address.street}). Station {target_station.name} has been notified."
                                # We pass it as a list because send_sms_broadcast expects a list
                                send_sms_broadcast([sensor.owner.phone_number], owner_msg)
                                print(f"Owner notified: {sensor.owner.phone_number}")

            return HttpResponse("1" if ml_result != "Safe" else "0")

        except Exception as e:
            print(f"❌ Error in receive_sensor_data: {e}")
            return HttpResponse("0")
    return HttpResponse("0", status=405)

# ==========================================send
# 2. MOBILIZE TEAM (CONFIRMATION)
# ==========================================
@login_required
def mobilize_team(request, report_id):
    """ 
    Called when the 'Mobilize Team' button is clicked.
    Assigns the currently on-duty staff to the report.
    """
    if request.method == "POST":
        try:
            report = Report.objects.get(id=report_id)
            now = timezone.now()
            
            # Find currently ON-DUTY staff at this station
            active_duties = DutyAssignment.objects.filter(
                firefighter__station=report.station,
                start_time__lte=now,
                end_time__gte=now,
                is_active=True
            )
            
            # Add them to the team history
            for duty in active_duties:
                report.mobilized_team.add(duty.firefighter)
            
            report.status = 'Confirmed'
            report.in_charge = request.user 
            report.save()
            
            return JsonResponse({'success': True, 'message': f'Mobilized {active_duties.count()} firefighters.'})
            
        except Report.DoesNotExist:
            return JsonResponse({'error': 'Report not found'}, status=404)

# ==========================================
# 3. MAP DATA (CRASH FIX)
# ==========================================
@login_required
def firefighter_map_data(request):
    """ Returns map data, filtering out users with NULL coordinates """
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'firefighter':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    data = []
    users = UserProfile.objects.filter(role='public').select_related('address')

    for profile in users:
        # CRITICAL FIX: Ignore if Lat/Lng is None to prevent map crash
        if profile.address and profile.address.latitude is not None and profile.address.longitude is not None:
            sensors = profile.sensors.all()
            house_status = "Safe"
            has_offline = False
            
            for s in sensors:
                s_status = get_sensor_status(s)
                if s_status == 'Fire':
                    house_status = 'Fire'
                    break 
                elif s_status == 'Gas Leak' and house_status != 'Fire':
                    house_status = 'Gas Leak'
                elif s_status == 'Offline':
                    has_offline = True

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
# 4. STANDARD PAGE VIEWS
# ==========================================
@login_required(login_url='login')
def dashboard(request):
    try: user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist: user_profile = UserProfile.objects.create(user=request.user)
    
    sensors = Sensor.objects.filter(owner=user_profile) if user_profile.role == 'public' else Sensor.objects.all()
    
    context = {
        'sensors_count': sensors.count(),
        'sensors': sensors,
        'ml_model_name': predictor.get_active_model_info(),
        'maintenance_pending': Maintenance.objects.filter(status='Pending').count(),
        'maintenance_items': Maintenance.objects.all().order_by('-timestamp'),
        'reports_count': Report.objects.count(),
        'recent_reports': Report.objects.all().order_by('-timestamp'),
        'stations_count': FireStation.objects.count(),
    }
    return render(request, 'sensors/dashboard.html', context)

@login_required(login_url='login')
def maps(request):
    try: user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist: return render(request, 'sensors/maps.html', {'role': 'unknown'})

    context = {'role': user_profile.role, 'user_profile': user_profile}

    if user_profile.role == 'public':
        user_layouts = Houselayout.objects.filter(user=request.user).order_by('id')
        selected_layout_id = request.GET.get('layout_id')
        current_layout = user_layouts.filter(id=selected_layout_id).first() if selected_layout_id else user_layouts.first()

        context['layouts'] = user_layouts
        context['current_layout'] = current_layout
        context['sensors'] = Sensor.objects.filter(owner=user_profile, layout=current_layout) if current_layout else []

    elif user_profile.role == 'firefighter':
        station = user_profile.station
        if not station: station = FireStation.objects.first()
        
        context['station_lat'] = float(station.address.latitude) if station and station.address else 1.8548
        context['station_lng'] = float(station.address.longitude) if station and station.address else 103.0848
        context['station_radius'] = math.sqrt(station.cover_area_sqm / math.pi) / 1000 if station and station.cover_area_sqm else 3.0
        context['station_name'] = station.name if station else "HQ"

    return render(request, 'sensors/maps.html', context)

@login_required(login_url='login')
@xframe_options_sameorigin
def duty(request):
    """ Shows shifts that are currently active or in the future """
    user_profile = UserProfile.objects.get(user=request.user)
    
    my_schedule = DutyAssignment.objects.filter(
        firefighter=user_profile,
        is_active=True,
        end_time__gte=timezone.now() # Show shifts that haven't ended yet
    ).order_by('start_time')
    
    return render(request, 'sensors/duty_popup.html', {'my_schedule': my_schedule})

@login_required(login_url='login')
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    current_address = user_profile.address
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        a_form = AddressUpdateForm(request.POST, instance=user_profile.address)
        if u_form.is_valid() and p_form.is_valid() and a_form.is_valid():
            u_form.save()
            p_form.save()
            address_instance = a_form.save()
            if not user_profile.address:
                user_profile.address = address_instance
                user_profile.save()
            messages.success(request, 'Profile updated!')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=user_profile)
        a_form = AddressUpdateForm(instance=current_address)
    context = {'u_form': u_form, 'p_form': p_form, 'a_form': a_form, 'user_profile': user_profile}
    return render(request, 'sensors/profile.html', context)

# ==========================================
# 5. AUTHENTICATION & OTHER VIEWS
# ==========================================
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'Logged out successfully!')
        return redirect('login')
    return redirect('home')

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
            messages.error(request, 'Registration failed.')
    else:
        form = SignUpForm()
    return render(request, 'sensors/auth/register.html', {'form': form})

@login_required(login_url='login')
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if not request.user.check_password(old_password):
            messages.error(request, 'Incorrect current password.')
        elif new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        else:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, 'Password changed!')
            return redirect('login')
    return render(request, 'sensors/change_password.html')

# ==========================================
# 6. MAINTENANCE & REPORTS
# ==========================================
@login_required(login_url='login')
def maintenance(request):
    user_role = getattr(request.user.userprofile, 'role', 'public')
    if user_role == 'public':
        maintenances = Maintenance.objects.all().order_by('-scheduled_date')
    else:
        maintenances = Maintenance.objects.filter(Q(status='Pending') | Q(in_charge=request.user)).order_by('-scheduled_date')
    return render(request, 'sensors/maintenance.html', {'maintenance_items': maintenances, 'user_role': user_role})

@login_required(login_url='login')
def maintenance_detail(request, maintenance_id):
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    if request.method == 'POST' and 'picture' in request.FILES:
        MaintenanceImage.objects.create(maintenance=maintenance, image=request.FILES['picture'])
        messages.success(request, 'Evidence uploaded!')
        return redirect('maintenance_detail', maintenance_id=maintenance.id)
    return render(request, 'sensors/maintenance_detail.html', {'maintenance': maintenance})

@login_required(login_url='login')
def create_maintenance(request):
    if request.method == 'POST':
        form = MaintenanceForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save()
            for img in request.FILES.getlist('images'):
                MaintenanceImage.objects.create(maintenance=m, image=img)
            return redirect('maintenance')
    else:
        form = MaintenanceForm()
    return render(request, 'sensors/maintenance_create.html', {'form': form})

def edit_maintenance(request, maintenance_id):
    task = get_object_or_404(Maintenance, id=maintenance_id)
    
    # 2. ROBUST: Explicitly fetch profile to ensure we get the correct role
    try:
        profile = UserProfile.objects.get(user=request.user)
        user_role = profile.role
    except UserProfile.DoesNotExist:
        user_role = 'public'

    if request.method == 'POST':
        if user_role == 'public':
            form = MaintenanceForm(request.POST, request.FILES, instance=task)
            if form.is_valid():
                m = form.save()
                # handle_images(request, m) # Ensure this helper exists or import it
                return redirect('maintenance_detail', maintenance_id=m.id)
        else:
            # Firefighter/Technician Logic
            task.status = request.POST.get('status')
            task.actual_date = request.POST.get('actual_date') or None # Handle empty strings
            task.technician_notes = request.POST.get('technician_notes')
            if not task.in_charge: 
                task.in_charge = request.user
            task.save()
            # handle_images(request, task)
            return redirect('maintenance_detail', maintenance_id=task.id)
    else:
        form = MaintenanceForm(instance=task)
        
    return render(request, 'sensors/maintenance_edit.html', {
        'form': form, 
        'maintenance': task, 
        'user_role': user_role
    })

def handle_images(request, maintenance_instance):
    for img in request.FILES.getlist('images'):
        MaintenanceImage.objects.create(maintenance=maintenance_instance, image=img)
    if request.POST.getlist('delete_images'):
        MaintenanceImage.objects.filter(id__in=request.POST.getlist('delete_images'), maintenance=maintenance_instance).delete()

@login_required(login_url='login')
def delete_maintenance(request, maintenance_id):
    get_object_or_404(Maintenance, id=maintenance_id).delete()
    return redirect('maintenance')

@login_required(login_url='login')
def reports(request):
    return render(request, 'sensors/reports.html', {'reports': Report.objects.all().order_by('-timestamp')})

@login_required(login_url='login')
def report_detail(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    is_firefighter = hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'firefighter'
    if request.method == 'POST' and is_firefighter:
        report.fire_type = request.POST.get('fire_type')
        report.cause = request.POST.get('cause')
        report.description = request.POST.get('description')
        report.status = request.POST.get('status')
        if request.POST.get('station'):
            report.station = FireStation.objects.get(id=request.POST.get('station'))
        report.in_charge = request.user
        report.save()
        for img in request.FILES.getlist('images'):
            ReportImage.objects.create(report=report, image=img)
        messages.success(request, 'Report updated!')
        return redirect('reports')
    return render(request, 'sensors/report_detail.html', {'report': report, 'stations': FireStation.objects.all(), 'is_firefighter': is_firefighter})

@login_required(login_url='login')
def create_report(request):
    if request.method == 'POST':
        try:
            station = FireStation.objects.get(id=request.POST.get('station'))
            address = Address.objects.get(id=request.POST.get('address')) if request.POST.get('address') else None
            report = Report.objects.create(
                status='Confirmed',
                fire_type=request.POST.get('fire_type'),
                cause=request.POST.get('cause'),
                description=request.POST.get('description'),
                station=station,
                address=address,
                in_charge=request.user
            )
            for img in request.FILES.getlist('images'):
                ReportImage.objects.create(report=report, image=img)
            return redirect('report_detail', report_id=report.id)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, 'sensors/create_report.html', {'stations': FireStation.objects.all(), 'addresses': Address.objects.all()})
# --- HELPER: Permission Check ---
def check_firefighter_role(user):
    """Ensures only firefighters can edit/delete"""
    if not hasattr(user, 'userprofile') or user.userprofile.role != 'firefighter':
        raise PermissionDenied("You do not have permission to perform this action.")

# --- UPDATE VIEW ---
@login_required(login_url='login')
def edit_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    
    # 1. Security Check
    check_firefighter_role(request.user)

    if request.method == 'POST':
        # Load form with POST data
        form = ReportUpdateForm(request.POST, instance=report)
        
        if form.is_valid():
            # Save basic data
            updated_report = form.save(commit=False)
            updated_report.in_charge = request.user 
            updated_report.save()

            # Handle Images (Keep your existing logic, it's good)
            handle_report_images(request, updated_report)

            messages.success(request, f'Report #{report.id} updated successfully!')
            return redirect('report_detail', report_id=report.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Load form with existing data
        form = ReportUpdateForm(instance=report)

    context = {
        'form': form,
        'report': report, 
    }
    return render(request, 'sensors/update_report.html', context)

# --- DELETE VIEW ---
@login_required(login_url='login')
@require_POST # Security: Prevent deletion via simple browser link click (GET)
def delete_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    
    # 1. Security Check
    check_firefighter_role(request.user)

    # 2. Cleanup: Delete image files associated with this report
    for img_obj in report.images.all():
        if img_obj.image and os.path.isfile(img_obj.image.path):
            os.remove(img_obj.image.path) # Delete file from disk
    
    # 3. Delete DB Record
    report_id_ref = report.id
    report.delete()
    
    messages.success(request, f'Report #{report_id_ref} deleted.')
    return redirect('reports')

# --- IMAGE HANDLER (Kept mostly same, added file cleanup) ---
def handle_report_images(request, report_instance):
    # 1. Add New Images
    for img in request.FILES.getlist('images'):
        ReportImage.objects.create(report=report_instance, image=img)
    
    # 2. Delete Selected Images
    delete_ids = request.POST.getlist('delete_images')
    if delete_ids:
        images_to_delete = ReportImage.objects.filter(
            id__in=delete_ids, 
            report=report_instance
        )
        # Delete actual files from disk before deleting DB record
        for img_obj in images_to_delete:
            if img_obj.image and os.path.isfile(img_obj.image.path):
                os.remove(img_obj.image.path)
        
        images_to_delete.delete()
# ==========================================
# 7. SENSOR & LAYOUT MANAGEMENT
# ==========================================
@login_required(login_url='login')
def upload_layout(request):
    if request.method == "POST":
        form = HouseLayoutForm(request.POST, request.FILES)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.user = request.user
            layout.save()
            return redirect('maps')
    else:
        form = HouseLayoutForm()
    return render(request, 'sensors/upload_layout.html', {'form': form, 'existing_layouts': Houselayout.objects.filter(user=request.user)})

@login_required
def get_live_data(request):
    try: sensors = Sensor.objects.filter(owner=request.user.userprofile).order_by('id')
    except: return JsonResponse({'sensors': []})
    data = [{'id': s.id, 'name': s.name, 'status': get_sensor_status(s), 'x': s.x_position, 'y': s.y_position} for s in sensors]
    return JsonResponse({'sensors': data})

@login_required
def get_victim_layout(request, user_id):
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'firefighter':
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    layouts = Houselayout.objects.filter(user_id=user_id).prefetch_related('sensors')
    results = []
    for l in layouts:
        sensors = [{'id': s.id, 'name': s.name, 'x': s.x_position, 'y': s.y_position, 'status': get_sensor_status(s)} for s in l.sensors.all()]
        results.append({'layout_id': l.id, 'layout_name': l.name, 'image_url': l.image.url, 'sensors': sensors})
    return JsonResponse({'success': True, 'layouts': results})

@csrf_exempt
@login_required
def add_sensor(request):
    if request.method == "POST":
        data = json.loads(request.body)
        layout = Houselayout.objects.get(id=data.get('layout_id'), user=request.user)
        new_sensor = Sensor.objects.create(owner=request.user.userprofile, name=data.get('name'), layout=layout)
        return JsonResponse({'success': True, 'sensor_id': new_sensor.id})
    return JsonResponse({'success': False})

@csrf_exempt
@login_required
def update_sensor_position(request):
    """
    Updates the X/Y coordinates of a sensor on the map.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # 1. MOVED: The get() query MUST be inside the try block
            sensor = Sensor.objects.get(id=data['sensor_id'], owner__user=request.user)
            
            sensor.x_position = data['x']
            sensor.y_position = data['y']
            sensor.save()
            
            return JsonResponse({'success': True})
            
        except (Sensor.DoesNotExist, KeyError, ValueError):
            # Returns JSON failure instead of crashing (500)
            return JsonResponse({'success': False, 'message': 'Sensor not found or access denied'})
            
    return JsonResponse({'success': False}, status=400)

@login_required
@require_POST
def delete_sensor_ajax(request, sensor_id):
    Sensor.objects.get(id=sensor_id, owner__user=request.user).delete()
    return JsonResponse({'success': True, 'message': 'Deleted'})

@login_required
@require_POST
def delete_layout_ajax(request, layout_id):
    Houselayout.objects.get(id=layout_id, user=request.user).delete()
    return JsonResponse({'success': True, 'message': 'Deleted'})

@login_required
@require_POST
def edit_layout_ajax(request):
    layout = Houselayout.objects.get(id=request.POST.get('layout_id'), user=request.user)
    if request.POST.get('name'): layout.name = request.POST.get('name')
    if 'image' in request.FILES: layout.image = request.FILES['image']
    layout.save()
    return JsonResponse({'success': True})

@login_required
def get_dashboard_sensor_data(request):
    user = request.user.userprofile
    sensors = Sensor.objects.filter(owner=user) if user.role == 'public' else Sensor.objects.all()
    data = []
    for s in sensors:
        log = s.readings.last()
        data.append({'id': s.id, 'temp': f"{log.dht22_temp:.1f}" if log else "N/A", 'hum': f"{log.humidity:.1f}" if log else "N/A", 'status': log.status if log else "N/A"})
    return JsonResponse({'sensors': data})

@login_required
def delete_sensor(request, sensor_id): # Fallback non-ajax delete
    if request.method == "POST":
        Sensor.objects.get(id=sensor_id, owner__user=request.user).delete()
        return redirect('dashboard')
    return redirect('dashboard')