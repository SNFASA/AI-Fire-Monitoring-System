from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Your other app URLs here...

    # Serve Manifest
    path('manifest.json', TemplateView.as_view(
        template_name='manifest.json', 
        content_type='application/json'
    ), name='manifest.json'),

    # Serve Service Worker
    path('sw.js', TemplateView.as_view(
        template_name='sw.js', 
        content_type='application/javascript'
    ), name='sw.js'),
]