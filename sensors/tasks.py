from celery import shared_task
from .services import fetch_and_filter_hotspots


@shared_task
def update_malaysia_hotspots():
    result = fetch_and_filter_hotspots()
    return result


import requests
from django.conf import settings

# 1. Check if Django is actually reading your .env file
print("My API Key is:", settings.MAP_KEY)

# 2. Construct the URL
url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{settings.MAP_KEY}/VIIRS_SNPP_NRT/{settings.REGION_BBOX}/1"
print("Requesting URL:", url)

# 3. Ask NASA for the data and print their exact response
response = requests.get(url)
print("NASA Status Code:", response.status_code)
print("NASA Response Text:", response.text)
