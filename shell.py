import math

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from sensors.models import (
    FireStation,
    Report,  # Adjust imports if needed
    SatelliteHotspot,
)

hotspot = SatelliteHotspot.objects.latest("id")
fire_lat = hotspot.location.y
fire_lon = hotspot.location.x

print(f"Testing SatelliteHotspot ID {hotspot.id} at ({fire_lat}, {fire_lon})")


def check_coverage(fire_lat, fire_lon):
    # Optimized query to fetch stations and their linked addresses in one go
    stations = FireStation.objects.select_related("address").all()

    for station in stations:
        # Safety check to ensure the station actually has coordinates assigned
        if (
            not hasattr(station, "address")
            or station.address.latitude is None
            or station.address.longitude is None
        ):
            print(f"Skipping {station.name}: Missing address or coordinates.")
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
        distance = c * 6371000

        coverage_radius = math.sqrt(station.cover_area_sqm / math.pi)
        print(
            f"Checking Station: {station.name} | Distance: {distance:.2f}m | Coverage Radius: {coverage_radius:.2f}m"
        )

        if distance <= coverage_radius:
            print(f"Match found! Creating report for {station.name}...")

            report = Report.objects.create(
                station=station,
                latitude=fire_lat,
                longitude=fire_lon,
                status="System Detected",
            )

            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"station_{station.id}",
                    {
                        "type": "fire_alert",
                        "data": {
                            "report_id": report.id,
                            "latitude": report.latitude,
                            "longitude": report.longitude,
                            "status": report.status,
                        },
                    },
                )
                print(f"WebSocket alert broadcasted to group: station_{station.id}")
            except Exception as e:
                print(f"WebSocket group_send failed: {e}")

            return report

    print("Hotspot is outside the coverage area of all registered stations.")
    return None


check_coverage(fire_lat, fire_lon)
