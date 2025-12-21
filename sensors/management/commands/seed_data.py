import random
from django.core.management.base import BaseCommand
from django.db import transaction
from sensors.models import UserProfile, Sensor, SensorDataLog, Report, FireStation, Maintenance
from sensors.tests.factories import (
    UserProfileFactory, SensorFactory, SensorDataLogFactory, 
    FireStationFactory, ReportFactory, ReportImageFactory
)

class Command(BaseCommand):
    help = "Generates dummy data for the Fire Monitoring System"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("🌱 Starting Database Seeder...")

        # 1. Create Fire Station & Chief
        station = FireStationFactory(name="Central HQ")
        chief = UserProfileFactory(user__username="chief_fire", user__password="password123", role="firefighter", station=station)
        self.stdout.write(f"✅ Created Chief Firefighter: 'chief_fire' (pass: password123)")

        # 2. Create Public Users (Victims)
        users = []
        for i in range(10):
            u = UserProfileFactory(user__username=f"public_user_{i}", user__password="password123", role="public")
            users.append(u)
        self.stdout.write(f"✅ Created 5 Public Users")

        # 3. Create Sensors & Logs
        all_sensors = []
        for user in users:
            # Each user gets 2-3 sensors
            for _ in range(random.randint(2, 3)):
                sensor = SensorFactory(owner=user)
                all_sensors.append(sensor)
                
                # Generate 20 SAFE logs for history
                SensorDataLogFactory.create_batch(20, sensor=sensor, status='Safe')

        self.stdout.write(f"✅ Created {len(all_sensors)} Sensors & {len(all_sensors)*20} Logs")

        # 4. Create Incidents (The Drama!)
        # Pick 2 random sensors to have a FIRE incident
        victim_sensors = random.sample(all_sensors, 2)
        
        for sensor in victim_sensors:
            # 1. Create the 'Fire' log
            SensorDataLogFactory(
                sensor=sensor,
                status='Fire',
                methane=1500,
                flame_val=100, # Fire detected
                dht22_temp=85.5
            )

            # 2. Auto-Create the System Report
            report = ReportFactory(
                status='System Detected',
                address=sensor.owner.address,
                trigger_sensor=sensor,
                trigger_temperature=85.5,
                trigger_gas_level=1500
            )
            
            # 3. Simulate Firefighter Confirmation (for one of them)
            if random.choice([True, False]):
                report.status = 'Confirmed'
                report.station = station
                report.in_charge = chief.user
                report.fire_type = "Electrical Fire"
                report.cause = "Short Circuit"
                report.description = "Firefighter arrived. Scene contained."
                report.save()
                
                # Add Evidence Photos
                ReportImageFactory.create_batch(2, report=report)

        self.stdout.write("✅ Created Fire Incidents & Reports")
        self.stdout.write("🌱 Seeding Complete!")