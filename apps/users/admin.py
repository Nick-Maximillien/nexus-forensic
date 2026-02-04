from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, LawyerProfile, NGOProfile, DonorProfile, AdminProfile

# ----------------- User Admin -----------------
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'username', 'role', 'wallet_address', 'public_key', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_staff', 'is_superuser')
    search_fields = ('email', 'username', 'wallet_address', 'public_key')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password', 'role', 'wallet_address', 'public_key')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'role', 'password1', 'password2', 'wallet_address', 'public_key'),
        }),
    )

admin.site.register(User, UserAdmin)

# ----------------- Role-specific Profiles -----------------
@admin.register(LawyerProfile)
class LawyerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialty', 'verified', 'cases_managed', 'rating')
    search_fields = ('user__email', 'specialty')

@admin.register(NGOProfile)
class NGOProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization_name', 'verified', 'funded_cases')
    search_fields = ('user__email', 'organization_name')

@admin.register(DonorProfile)
class DonorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'contribution_count', 'total_contributed')
    search_fields = ('user__email', 'display_name')

@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'permissions')
    search_fields = ('user__email',)
