# backend/apps/users/urls.py

from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView,
    CustomTokenObtainPairView,
    RoleProfileView,
    MirrorUserView,
    HealthCheckView,
    create_superuser_view
)

urlpatterns = [
    # ----------------- Auth -----------------
    path('signup/', SignupView.as_view(), name='signup'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('mirror/', MirrorUserView.as_view(), name='mirror-user'),

    # ----------------- Role-specific profile -----------------
    path('profile/', RoleProfileView.as_view(), name='role-profile'),



    # ----------------- Admin / Dev -----------------
    path('create-superuser/', create_superuser_view, name='create-superuser'),

    # ----------------- Health Check -----------------
    path('health/', HealthCheckView.as_view(), name='health_check'),
]

# Serve media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
