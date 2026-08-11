from django.db.models.signals import post_save
from django.contrib.auth.models import User

def populate_models(sender, **kwargs):
    from django.contrib.auth.models import User, Group, Permission

    # create groups
    person, created = Group.objects.get_or_create(name='person')
    vendor, created = Group.objects.get_or_create(name='vendor')

def create_user_profile(sender, instance, created, **kwargs):
    if created:
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=instance)

post_save.connect(create_user_profile, sender=User)
