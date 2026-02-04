# apps/users/signals.py
import requests
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import LawyerProfile, NGOProfile, DonorProfile, AdminProfile

User = get_user_model()

NODE_WALLET_SERVER_URL = getattr(settings, "NODE_WALLET_SERVER_URL", "http://localhost:4000/create-wallet")

def trigger_wallet_creation(instance_id, instance_email):
    """Function to execute the external API call."""
    try:
        payload = {
            "userId": str(instance_id),
            "email": instance_email
        }
        # Note: A separate, non-blocking task queue (like Celery) is ideal for external calls.
        # But for synchronous simplicity, we keep the requests.post here.
        response = requests.post(NODE_WALLET_SERVER_URL, json=payload, timeout=5)
        response.raise_for_status()
        print(f"Node.js wallet server response: {response.json()}")
    except requests.RequestException as e:
        print(f"⚠️ Failed to create wallet for user {instance_id}: {e}")


@receiver(post_save, sender=User)
def create_role_profile(sender, instance, created, **kwargs):
    """
    Automatically create role-specific profiles and trigger Node.js wallet creation.
    """
    if not created:
        # Crucial check: only run this logic for new users
        return

    # 1. Create Role-Specific Profiles (Existing Logic)
    role = instance.role

    # -------- LAWYER --------
    if role == User.Roles.LAWYER:
        profile, _ = LawyerProfile.objects.get_or_create(user=instance)
        if instance.practicing_certificate:
            profile.specialty = instance.practicing_certificate
        profile.save()

    # -------- NGO --------
    elif role == User.Roles.NGO:
        profile, _ = NGOProfile.objects.get_or_create(user=instance)
        if instance.full_name:
            profile.organization_name = instance.full_name
        profile.save()

    # -------- DONOR --------
    elif role == User.Roles.DONOR:
        profile, _ = DonorProfile.objects.get_or_create(user=instance)
        profile.display_name = instance.full_name or instance.email.split("@")[0]
        profile.save()

    # -------- ADMIN --------
    elif role == User.Roles.ADMIN:
        AdminProfile.objects.get_or_create(user=instance)

    # 2. Trigger Node.js wallet creation ONLY after commit
    # V V V FIX: Use transaction.on_commit V V V
    # This ensures the Node.js server is not contacted until the Django User 
    # and all profiles are safely written to the database.
    # transaction.on_commit(lambda: trigger_wallet_creation(instance.id, instance.email))
    # ^ ^ ^ FIX: Use transaction.on_commit V V V