from .models import BusinessProfile


    

def get_or_create_business(user, phone=None, name=None):
    business, created = BusinessProfile.objects.get_or_create(user=user)
    if phone:
        business.phone = phone
    if name:
        business.name = name
    if phone or name:
        business.save()
    return business    
    
  
