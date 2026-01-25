"""
Basic tests for accounts app
"""
from django.test import TestCase
from apps.accounts.models import Organization


class OrganizationModelTest(TestCase):
    """Test Organization model"""

    def test_organization_creation(self):
        """Test creating an organization"""
        org = Organization.objects.create(
            name="Test Organization",
            business_type=Organization.BusinessType.RESTAURANT
        )
        self.assertEqual(org.name, "Test Organization")
        self.assertEqual(org.business_type, Organization.BusinessType.RESTAURANT)
        self.assertTrue(org.is_active)
        self.assertIsNotNone(org.widget_key)

    def test_organization_str(self):
        """Test organization string representation"""
        org = Organization.objects.create(
            name="Test Org"
        )
        self.assertEqual(str(org), "Test Org")

    def test_organization_power_plan(self):
        """Test power plan property"""
        org = Organization.objects.create(
            name="Power Org",
            plan=Organization.Plan.POWER
        )
        self.assertTrue(org.is_power_plan)

        basic_org = Organization.objects.create(
            name="Basic Org",
            plan=Organization.Plan.BASIC
        )
        self.assertFalse(basic_org.is_power_plan)
