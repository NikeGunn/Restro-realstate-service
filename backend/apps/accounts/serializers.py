"""
Accounts serializers for API.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Organization, Location, OrganizationMembership

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name', 'phone', 'password', 'password_confirm']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone', '')
        )
        
        # Don't auto-create organization - let user choose business type in setup flow
        
        return user


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for Location model."""

    class Meta:
        model = Location
        fields = [
            'id', 'name', 'address_line1', 'address_line2', 'city', 'state',
            'postal_code', 'country', 'email', 'phone', 'timezone',
            'is_primary', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LocationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating locations."""

    class Meta:
        model = Location
        fields = [
            'name', 'address_line1', 'address_line2', 'city', 'state',
            'postal_code', 'country', 'email', 'phone', 'timezone', 'is_primary'
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""
    locations = LocationSerializer(many=True, read_only=True)
    locations_count = serializers.SerializerMethodField()
    is_power_plan = serializers.BooleanField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'business_type', 'plan', 'email', 'phone', 'website',
            'widget_key', 'widget_color', 'widget_position', 'widget_greeting',
            'is_active', 'created_at', 'updated_at', 'locations', 'locations_count',
            'is_power_plan'
        ]
        read_only_fields = ['id', 'widget_key', 'created_at', 'updated_at', 'is_power_plan']

    def get_locations_count(self, obj):
        return obj.locations.filter(is_active=True).count()


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating organizations."""

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'business_type', 'email', 'phone', 'website',
            'widget_color', 'widget_position', 'widget_greeting', 'widget_key'
        ]
        read_only_fields = ['id', 'widget_key']


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    """Serializer for OrganizationMembership model."""
    user = UserSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    locations = LocationSerializer(many=True, read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ['id', 'user', 'organization', 'role', 'locations', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrganizationMembershipCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating memberships."""
    user_email = serializers.EmailField(write_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ['user_email', 'role', 'locations']

    def validate_user_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('User with this email does not exist.')
        return value

    def create(self, validated_data):
        user_email = validated_data.pop('user_email')
        user = User.objects.get(email=user_email)
        locations = validated_data.pop('locations', [])
        membership = OrganizationMembership.objects.create(user=user, **validated_data)
        if locations:
            membership.locations.set(locations)
        return membership


class CurrentUserSerializer(serializers.ModelSerializer):
    """Serializer for current authenticated user with organizations."""
    organizations = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone', 'date_joined', 'organizations']
        read_only_fields = ['id', 'date_joined']

    def get_organizations(self, obj):
        memberships = obj.memberships.select_related('organization').all()
        return [
            {
                'id': m.organization.id,
                'name': m.organization.name,
                'business_type': m.organization.business_type,
                'plan': m.organization.plan,
                'role': m.role,
            }
            for m in memberships
        ]
