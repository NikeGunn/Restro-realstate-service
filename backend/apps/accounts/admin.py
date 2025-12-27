"""
Admin configuration for accounts app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Organization, Location, OrganizationMembership


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-date_joined']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'business_type', 'plan', 'is_active', 'created_at']
    list_filter = ['business_type', 'plan', 'is_active']
    search_fields = ['name', 'email']
    readonly_fields = ['widget_key', 'created_at', 'updated_at']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'city', 'is_primary', 'is_active']
    list_filter = ['is_primary', 'is_active', 'organization']
    search_fields = ['name', 'city', 'organization__name']


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'created_at']
    list_filter = ['role', 'organization']
    search_fields = ['user__email', 'organization__name']
