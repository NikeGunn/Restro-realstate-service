"""
Shared ViewSet mixins (Phase 0).

Two cross-cutting invariants, generalized from apps/inventory:

1. OrgScopeMixin  — querysets are ALWAYS scoped to the user's membership orgs;
   optional ?organization= / ?location= narrow further but only after verifying
   membership; cross-org object access returns 404 (don't leak existence);
   writes require owner role on the payload's org.

2. AuditLoggedMixin — auto-logs create/update/destroy with before/after JSON +
   computed diff to a pluggable audit-log model (override get_audit_log_model()).
"""
import logging

from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import OrganizationMembership, Location
from .utils import client_ip, model_to_dict, diff

logger = logging.getLogger(__name__)


class OrgScopeMixin:
    """
    Mix into any ViewSet whose model has an `organization` FK (and optionally
    a `location` FK). Behavior is identical to the proven inventory mixin.
    """

    def _user_org_ids(self):
        return list(
            OrganizationMembership.objects.filter(user=self.request.user)
            .values_list('organization_id', flat=True)
        )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
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

    def get_object(self):
        """
        Cross-org object access returns 404 (not 403) so we never leak the
        existence of another org's row. Because get_queryset() is already
        org-scoped, DRF's default lookup naturally 404s out-of-scope ids — we
        keep this override explicit so the contract is obvious and stable.
        """
        try:
            return super().get_object()
        except (PermissionDenied,):
            # Defensive: never convert an in-scope perm error, but an
            # out-of-scope lookup should already be a 404 from the scoped qs.
            raise Http404

    def perform_create(self, serializer):
        org = serializer.validated_data.get('organization')
        org_id = getattr(org, 'id', org)
        if not org_id:
            raise ValidationError({'organization': 'organization is required.'})
        is_owner = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id,
            role=OrganizationMembership.Role.OWNER,
        ).exists()
        if not is_owner:
            raise PermissionDenied(
                "Only the organization owner can create records here."
            )
        self._save_with_creator(serializer)

    def _save_with_creator(self, serializer):
        """
        Save, passing created_by only if the model accepts it. Keeps the mixin
        usable on models that don't track a creator without crashing.
        """
        model = serializer.Meta.model
        field_names = {f.name for f in model._meta.get_fields()}
        if 'created_by' in field_names:
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()


class AuditLoggedMixin:
    """
    Auto-log create/update/destroy with before/after JSON + diff.

    Override `get_audit_log_model()` to point at the app's audit model. The
    inventory subclass returns InventoryAuditLog so existing behavior is
    unchanged; new apps return their own. Audit failures are swallowed —
    auditing must never break the request.
    """
    audit_model_name = None
    audit_log_model = None  # may be set as a class attr instead of overriding the method

    def get_audit_log_model(self):
        if self.audit_log_model is None:
            raise NotImplementedError(
                "Set `audit_log_model` or override get_audit_log_model()."
            )
        return self.audit_log_model

    def _resolve_org(self, instance):
        org = getattr(instance, 'organization', None)
        if org is not None:
            return org
        # Fallback chain for models scoped via a parent (item / stock_take / etc.)
        for parent_attr in ('item', 'stock_take', 'recipe', 'customer', 'campaign', 'job'):
            parent = getattr(instance, parent_attr, None)
            if parent is not None:
                parent_org = getattr(parent, 'organization', None)
                if parent_org is not None:
                    return parent_org
        return None

    def _audit(self, action, instance, before=None, after=None):
        try:
            self.get_audit_log_model().objects.create(
                organization=self._resolve_org(instance),
                location=getattr(instance, 'location', None),
                action=action,
                model_name=self.audit_model_name or type(instance).__name__,
                object_id=instance.id,
                object_repr=str(instance)[:200],
                before=before,
                after=after,
                diff=diff(before, after) if (before and after) else None,
                performed_by=(
                    self.request.user if self.request.user.is_authenticated else None
                ),
                ip_address=client_ip(self.request),
            )
        except Exception:
            logger.exception('Audit log write failed')

    def perform_create(self, serializer):
        super().perform_create(serializer)
        instance = serializer.instance
        self._audit('create', instance, after=model_to_dict(instance))

    def perform_update(self, serializer):
        before = model_to_dict(self.get_object())
        super().perform_update(serializer)
        self._audit('update', serializer.instance,
                    before=before, after=model_to_dict(serializer.instance))

    def perform_destroy(self, instance):
        before = model_to_dict(instance)
        org = self._resolve_org(instance)
        loc = getattr(instance, 'location', None)
        model_name = self.audit_model_name or type(instance).__name__
        instance_id = instance.id
        instance_repr = str(instance)[:200]
        super().perform_destroy(instance)
        try:
            self.get_audit_log_model().objects.create(
                organization=org, location=loc,
                action='delete', model_name=model_name,
                object_id=instance_id, object_repr=instance_repr,
                before=before,
                performed_by=(
                    self.request.user if self.request.user.is_authenticated else None
                ),
                ip_address=client_ip(self.request),
            )
        except Exception:
            logger.exception('Audit log write failed (destroy)')
