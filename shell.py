import math
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from sensors.models import (
    FireStation,
    Report,
    Address,
    SatelliteHotspot,
)

def check_coverage(fire_lat, fire_lon, hotspot_instance):
    """
    Evaluates registered fire station radii against a hotspot location.
    If inside coverage, handles ORM creation and dispatches flat payload alerts.
    """
    # Optimized query to fetch stations and their linked addresses in one go
    stations = FireStation.objects.select_related("address").all()
    match_found = False

    for station in stations:
        # Safety check to ensure the station actually has coordinates assigned
        if (
            not hasattr(station, "address")
            or station.address.latitude is None
            or station.address.longitude is None
        ):
            print(f"⚠️ Skipping {station.name}: Missing address or coordinates.")
            continue

        # Pulling coordinates from the related Address model
        lat1, lon1, lat2, lon2 = map(
            math.radians,
            [fire_lat, fire_lon, station.address.latitude, station.address.longitude],
        )

        # Haversine math
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance = c * 6371000  # Radius of Earth in meters

        coverage_radius = math.sqrt(station.cover_area_sqm / math.pi)
        print(
            f"🔍 Checking Station: {station.name} | Distance: {distance:.2f}m | Coverage Radius: {coverage_radius:.2f}m"
        )

        if distance <= coverage_radius:
            print(f"🔥 Match found! Creating report context for {station.name}...")

            # FIX 1: Generate an Address object to store raw coordinates safely
            wildfire_address = Address.objects.create(
                street="Satellite Detected Hotspot Area",
                city="Wildfire Zone",
                state=station.address.state,
                postal_code=station.address.postal_code,
                latitude=fire_lat,
                longitude=fire_lon
            )

            # FIX 2: Instantiate using valid schema fields
            report = Report.objects.create(
                status="System Detected",
                address=wildfire_address,
                station=station,
                description=(
                    f"Automated Satellite Wildfire Alert.\n"
                    f"Thermal Brightness: {hotspot_instance.brightness if hasattr(hotspot_instance, 'brightness') else 'N/A'}K\n"
                    f"Fire Radiative Power (FRP): {hotspot_instance.frp if hasattr(hotspot_instance, 'frp') else 'N/A'} MW"
                ),
                fire_type="Wildfire / Bushfire"
            )

            # FIX 3: Flattened payload structure mapping directly to FireAlertConsumer fields
            try:
                channel_layer = get_channel_layer()
                payload = {
                    "type": "fire_alert",
                    "report_id": report.id,
                    "address": f"{wildfire_address.street} ({station.address.city})",
                    "owner_name": "SATELLITE_SYSTEM",
                    "lat": float(fire_lat),
                    "lng": float(fire_lon),
                    "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                
                # Dynamic group routing paths
                async_to_sync(channel_layer.group_send)(f"station_{station.id}", payload)
                async_to_sync(channel_layer.group_send)("station_all", payload)
                
                print(f"📡 WebSocket alert broadcasted to station_{station.id} and station_all successfully.")
            except Exception as e:
                print(f"❌ WebSocket group_send failed: {e}")

            match_found = True

    if not match_found:
        print("ℹ️ Hotspot is outside the coverage area of all registered stations.")


# FIX 4: Encapsulate immediate script execution using main block protection
if __name__ == "__main__":
    try:
        latest_hotspot = SatelliteHotspot.objects.latest("id")
        target_lat = latest_hotspot.location.y
        target_lon = latest_hotspot.location.x

        print(f"🚀 Running coverage test on SatelliteHotspot ID #{latest_hotspot.id} at ({target_lat}, {target_lon})")
        check_coverage(target_lat, target_lon, latest_hotspot)
        
    except SatelliteHotspot.DoesNotExist:
        print("❌ Error: No SatelliteHotspot entries found in the database to execute test pipeline.")