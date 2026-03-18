import requests
import json
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import GEOSGeometry
from sensors.models import CountryBoundary # Change 'sensors' to your actual app name!

class Command(BaseCommand):
    help = 'Fetches and loads the Malaysia GeoJSON boundary into the database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Fetching map data...")
        # Public, highly accurate GeoJSON repository
        url = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/MYS.geo.json"
        
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            
            # Convert the JSON geometry into a format PostGIS understands
            geom_str = json.dumps(data['features'][0]['geometry'])
            geom = GEOSGeometry(geom_str)
            
            # Save it to the database
            CountryBoundary.objects.update_or_create(
                name="Malaysia",
                defaults={'geom': geom}
            )
            self.stdout.write(self.style.SUCCESS('Successfully loaded the exact borders of Malaysia!'))
        else:
            self.stdout.write(self.style.ERROR('Failed to download map data.'))