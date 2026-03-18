import requests
import pandas as pd
from io import StringIO
from django.contrib.gis.geos import Point
from .models import SatelliteHotspot, CountryBoundary
from core.settings import MAP_KEY, REGION_BBOX


def fetch_and_filter_hotspots():
    # Construct the URL cleanly using the string from settings
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/{REGION_BBOX}/1"

    response = requests.get(url)
    if response.status_code != 200:
        return f"Failed to fetch data from NASA. Status: {response.status_code}"

    df = pd.read_csv(StringIO(response.text))

    # Get the exact borders of Malaysia from our database
    try:
        malaysia = CountryBoundary.objects.get(name="Malaysia")
    except CountryBoundary.DoesNotExist:
        return "Error: Malaysia boundary not loaded in database."

    hotspots_to_create = []

    for _, row in df.iterrows():
        # 1. Create a spatial point (GeoDjango uses Longitude, Latitude order!)
        fire_point = Point(row["longitude"], row["latitude"], srid=4326)

        # 2. THE STRICT FILTER: Does Malaysia's polygon contain this exact point?
        if malaysia.geom.contains(fire_point):

            # 3. Prevent duplicate entries
            if not SatelliteHotspot.objects.filter(
                location=fire_point, acq_time=row["acq_time"]
            ).exists():
                hotspots_to_create.append(
                    SatelliteHotspot(
                        location=fire_point,
                        brightness=row["bright_ti4"],
                        acq_date=row["acq_date"],
                        acq_time=row["acq_time"],
                        satellite="VIIRS",
                        confidence=row["confidence"],
                        frp=row["frp"],
                    )
                )

    SatelliteHotspot.objects.bulk_create(hotspots_to_create)
    return f"Strictly filtered and saved {len(hotspots_to_create)} hotspots inside Malaysia."
