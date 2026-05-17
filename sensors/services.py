import logging
import requests
import pandas as pd
from io import StringIO
from django.contrib.gis.geos import Point
from .models import SatelliteHotspot, CountryBoundary
from .utils import process_hotspot_coverage
from core.settings import MAP_KEY, REGION_BBOX
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

def fetch_and_filter_hotspots():
    # We will loop through these one by one
    sources = ["VIIRS_SNPP_NRT", "MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
    
    try:
        malaysia = CountryBoundary.objects.get(name="Malaysia")
    except CountryBoundary.DoesNotExist:
        return "Error: Malaysia boundary not loaded in database."

    # OPTIMIZATION: Fetch existing signatures from the last 7 days to prevent duplicates
    time_threshold = timezone.now() - timedelta(days=7)
    existing_hotspots = SatelliteHotspot.objects.filter(created_at__gte=time_threshold)
    existing_signatures = {
        f"{h.location.y},{h.location.x},{h.acq_date},{h.acq_time}" for h in existing_hotspots
    }

    hotspots_to_create = []

    # FIX: Ask NASA for each satellite's data individually
    for source in sources:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{REGION_BBOX}/5"

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()  
        except requests.exceptions.RequestException as e:
            logger.error(f"NASA API Error for {source}: {e}")
            continue  # Skip to the next satellite instead of crashing the whole script!

        try:
            df = pd.read_csv(StringIO(response.text))
        except Exception as e:
            logger.error(f"CSV parsing error for {source}: {e}")
            continue

        if df.empty:
            continue
        for _, row in df.iterrows():
            fire_point = Point(row["longitude"], row["latitude"], srid=4326)

            if malaysia.geom.contains(fire_point):
                signature = f"{row['latitude']},{row['longitude']},{row['acq_date']},{row['acq_time']}"
                
                if signature not in existing_signatures:
                    
                    if pd.notna(row.get("bright_ti4")):
                        bright_val = row["bright_ti4"]
                    else:
                        bright_val = row.get("brightness", 0)

                    # Get the instrument name, or default to the prefix of the source string
                    sat_name = row.get("instrument", source.split('_')[0])

                    hotspots_to_create.append(
                        SatelliteHotspot(
                            location=fire_point,
                            brightness=bright_val,
                            acq_date=row["acq_date"],
                            acq_time=row["acq_time"],  
                            satellite=sat_name,
                            confidence=str(row["confidence"]), 
                            frp=row["frp"] if pd.notna(row.get("frp")) else 0.0, 
                        )
                    )
                    existing_signatures.add(signature) 

    if not hotspots_to_create:
        return "NASA connected successfully, but no new hotspots to add."

    created_hotspots = SatelliteHotspot.objects.bulk_create(hotspots_to_create)
    
    alerts_triggered = 0
    for new_hotspot in created_hotspots:
        matched = process_hotspot_coverage(new_hotspot)
        if matched:
            alerts_triggered += 1

    return f"Successfully fetched and saved {len(created_hotspots)} new NASA hotspots! Triggered {alerts_triggered} station alerts."