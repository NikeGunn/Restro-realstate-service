"""
Accounts models - User, Organization, Location, Role
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with UUID primary key."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name='email address')
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use email as username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'users'
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return self.email


class Organization(models.Model):
    """
    Business/Organization entity.
    Can be a restaurant, real estate agency, etc.
    """
    class BusinessType(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurant'
        REAL_ESTATE = 'real_estate', 'Real Estate'

    class Plan(models.TextChoices):
        BASIC = 'basic', 'Basic'
        POWER = 'power', 'Power'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.RESTAURANT
    )
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.BASIC
    )

    # Contact info
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Widget settings
    widget_key = models.UUIDField(default=uuid.uuid4, unique=True)
    widget_color = models.CharField(max_length=7, default='#3B82F6')  # Tailwind blue-500
    widget_position = models.CharField(max_length=20, default='bottom-right')
    widget_greeting = models.TextField(default='Hello! How can I help you today?')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_power_plan(self):
        return self.plan == self.Plan.POWER


class Location(models.Model):
    """
    Physical location/branch of an organization.
    Basic plan: 1 location, Power plan: unlimited.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='locations'
    )
    name = models.CharField(max_length=255)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='USA')

    # Contact (can override org-level)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Timezone for scheduling
    timezone = models.CharField(max_length=50, default='America/New_York')

    # Flags
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'locations'
        ordering = ['-is_primary', 'name']

    def __str__(self):
        return f"{self.organization.name} - {self.name}"

    def save(self, *args, **kwargs):
        # Ensure only one primary location per org
        if self.is_primary:
            Location.objects.filter(
                organization=self.organization,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class OrganizationMembership(models.Model):
    """
    Links users to organizations with roles.
    One user can belong to multiple organizations.
    """
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        MANAGER = 'manager', 'Manager'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MANAGER
    )

    # Location-level access (null = all locations)
    locations = models.ManyToManyField(
        Location,
        blank=True,
        related_name='memberships'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organization_memberships'
        unique_together = ['user', 'organization']

    def __str__(self):
        return f"{self.user.email} - {self.organization.name} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    def has_location_access(self, location):
        """Check if user has access to a specific location."""
        if self.is_owner:
            return True
        if not self.locations.exists():
            return True  # Access to all locations
        return self.locations.filter(pk=location.pk).exists()
