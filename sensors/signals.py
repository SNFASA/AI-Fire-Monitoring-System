from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Check if profile already exists to avoid errors
        if not hasattr(instance, 'userprofile'):
            UserProfile.objects.create(user=instance, role='public')

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Save the profile whenever the user is saved
    if hasattr(instance, 'userprofile'):
        instance.userprofile.save()