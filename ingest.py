import json
import os
import django
from django.contrib.gis.geos import GEOSGeometry

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from sensors.models import CountryBoundary

def load_malaysia():
    file_path = 'malaysia.json'
    with open(file_path, 'r') as f:
        data = json.load(f)
        
    # Assuming standard GeoJSON structure
    for feature in data['features']:
        geom = GEOSGeometry(json.dumps(feature['geometry']))
        name = feature['properties'].get('name', 'Malaysia')
        
        # Create the record in the DB
        obj, created = CountryBoundary.objects.get_or_create(name=name, defaults={'geom': geom})
        if created:
            print(f"Successfully added: {name}")
        else:
            print(f"Boundary {name} already exists.")

if __name__ == "__main__":
    load_malaysia()
