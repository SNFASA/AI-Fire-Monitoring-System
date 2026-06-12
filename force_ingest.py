import os
import django
import json
from django.contrib.gis.geos import GEOSGeometry

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from sensors.models import CountryBoundary

def force_load():
    with open('all_countries.json', 'r') as f:
        data = json.load(f)
    
    # Let's inspect the first feature to see the keys
    first_feature = data['features'][0]
    print(f"Available keys in properties: {list(first_feature['properties'].keys())}")
    
    # Try common keys for country name
    possible_keys = ['ADMIN', 'name', 'NAME', 'sovereignt', 'ISO_A3']
    
    for feature in data.get('features', []):
        props = feature['properties']
        
        # Check all possible name keys
        country_name = None
        for key in possible_keys:
            if props.get(key) == 'Malaysia':
                country_name = 'Malaysia'
                break
        
        if country_name:
            print("Found Malaysia! Ingesting geometry...")
            geom_data = json.dumps(feature['geometry'])
            geom = GEOSGeometry(geom_data, srid=4326)
            
            CountryBoundary.objects.update_or_create(
                name='Malaysia',
                defaults={'geom': geom}
            )
            print("Success! Data ingested.")
            return

    print("Still could not find 'Malaysia'. Please check the printed keys above.")

if __name__ == "__main__":
    force_load()
