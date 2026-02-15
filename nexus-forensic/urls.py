"""
URL configuration for nexus forensic project.


"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # ----------------- Django Admin -----------
    path('admin/', admin.site.urls),

    # ----------------- Users App ---------------
    path('users/', include('apps.users.urls')),
    # ----------------- Forensic Agent App -----
    path('forensic/', include('apps.forensic_agent.urls')),

]
