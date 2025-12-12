
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.forms import ModelForm
from .models import UserProfile, Address, Houselayout, Sensor, SensorDataLog, Maintenance, Report

class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(max_length=254, required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
class AddressUpdateForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['street', 'city', 'state', 'postal_code']
class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(max_length=254, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']  
    
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'profile_picture']
        
class SensorPlacementForm(forms.ModelForm):
    class Meta: 
        model = Sensor
        fields = ['name','x_position', 'y_position']
        widgets={
            'x_position': forms.HiddenInput(),
            'y_position': forms.HiddenInput(),
        }
class HouseLayoutForm(forms.ModelForm):
    class Meta:
        model = Houselayout
        fields = ['name', 'image']