"""
Mixins for inventory ViewSets.

Two cross-cutting invariants enforced here:
1. Querysets are ALWAYS scoped to the organizations the user is a member of.
2. Optional `organization` and `location` query params narrow further, but
   only after we've verified the user actually belongs to that organization.
"""
from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.accounts.models import OrganizationMembership, Location, Organization


class InventoryOrgScopeMixin:
    """
    Mix into every inventory ViewSet. Assumes the model has FK fields
    `organization` and (optionally) `location`.
    """

    def _user_org_ids(self):
        return list(
            OrganizationMembership.objects.filter(user=self.request.user)
            .values_list('organization_id', flat=True)
        )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()

        org_ids = self._user_org_ids()
        qs = qs.filter(organization_id__in=org_ids)

        org_id = self.request.query_params.get('organization')
        if org_id:
            if org_id not in {str(x) for x in org_ids}:
                raise PermissionDenied("You are not a member of that organization.")
            qs = qs.filter(organization_id=org_id)

        location_id = self.request.query_params.get('location')
        if location_id:
            if not Location.objects.filter(
                id=location_id, organization_id__in=org_ids
            ).exists():
                raise PermissionDenied("Location does not belong to your organization.")
            qs = qs.filter(location_id=location_id)

        return qs

    def perform_create(self, serializer):
        # Ensure org provided in payload is one the user can write to.
        org_id = serializer.validated_data.get('organization')
        if hasattr(org_id, 'id'):
            org_id = org_id.id
        if not org_id:
            raise ValidationError({'organization': 'organization is required.'})
        membership = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id,
            role=OrganizationMembership.Role.OWNER,
        ).first()
        if not membership:
            raise PermissionDenied(
                "Only the organization owner can create inventory records."
            )
        serializer.save(created_by=self.request.user)
