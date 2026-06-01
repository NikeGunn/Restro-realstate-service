"""
CRM API (Phase 1) — mounted at /api/v1/crm/.

Read = owner|manager (IsOrgMember); write/delete/merge = owner (IsOrgOwner).
Every ViewSet uses the shared OrgScopeMixin; cross-org access returns 404.
Querysets are prefetch-optimized to avoid N+1 on tag rendering.
"""
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import OrgScopeMixin
from apps.common.permissions import IsOrgMember, IsOrgOwner

from .models import (
    CRMCustomer, CRMTag, CRMCustomerTag, CRMInteraction, CRMConsent, CRMSegment,
)
from .serializers import (
    CRMCustomerSerializer, CRMTagSerializer, CRMInteractionSerializer,
    CRMConsentSerializer, CRMSegmentSerializer,
    TagActionSerializer, ConsentRecordSerializer, MergeSerializer,
    SegmentPreviewSerializer,
)
from .services import customer_service, consent_service, segment_service


_TAG_PREFETCH = Prefetch(
    'customer_tags',
    queryset=CRMCustomerTag.objects.select_related('tag'),
)


class CRMCustomerViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = CRMCustomer.objects.all().prefetch_related(_TAG_PREFETCH)
    serializer_class = CRMCustomerSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['source', 'marketing_consent_status', 'is_active', 'gender']
    search_fields = ['name', 'phone', 'email', 'whatsapp_number']
    ordering_fields = ['created_at', 'last_visit_date', 'visit_count', 'name']

    @action(detail=True, methods=['get', 'post'])
    def tags(self, request, pk=None):
        """GET lists the customer's tags; POST adds/removes one (owner only)."""
        customer = self.get_object()
        if request.method == 'GET':
            tags = [ct.tag for ct in customer.customer_tags.select_related('tag')]
            return Response(CRMTagSerializer(tags, many=True).data)

        if not IsOrgOwner().has_object_permission(request, self, customer):
            return Response(status=status.HTTP_403_FORBIDDEN)
        s = TagActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tag = get_object_or_404(
            CRMTag, pk=s.validated_data['tag_id'], organization=customer.organization
        )
        if s.validated_data['action'] == 'add':
            CRMCustomerTag.objects.get_or_create(
                customer=customer, tag=tag, defaults={'added_by': request.user}
            )
        else:
            CRMCustomerTag.objects.filter(customer=customer, tag=tag).delete()
        tags = [ct.tag for ct in customer.customer_tags.select_related('tag')]
        return Response(CRMTagSerializer(tags, many=True).data)

    @action(detail=True, methods=['get'])
    def interactions(self, request, pk=None):
        customer = self.get_object()
        qs = customer.interactions.all()
        page = self.paginate_queryset(qs)
        ser = CRMInteractionSerializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @action(detail=True, methods=['get'])
    def consents(self, request, pk=None):
        customer = self.get_object()
        ser = CRMConsentSerializer(customer.consent_records.all(), many=True)
        return Response(ser.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgOwner])
    def merge(self, request, pk=None):
        """Merge a duplicate into this (primary) customer. Owner only."""
        primary = self.get_object()
        s = MergeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        duplicate = get_object_or_404(
            self.get_queryset(), pk=s.validated_data['duplicate_id']
        )
        merged = customer_service.merge_customers(primary, duplicate)
        return Response(CRMCustomerSerializer(merged).data)


class CRMTagViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = CRMTag.objects.all()
    serializer_class = CRMTagSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    search_fields = ['name']

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("System tags cannot be deleted.")
        instance.delete()


class CRMInteractionViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CRMInteraction.objects.select_related('customer').all()
    serializer_class = CRMInteractionSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['customer', 'interaction_type']
    ordering_fields = ['created_at']


class CRMConsentViewSet(OrgScopeMixin, viewsets.ReadOnlyModelViewSet):
    queryset = CRMConsent.objects.select_related('customer').all()
    serializer_class = CRMConsentSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    filterset_fields = ['customer', 'consent_given', 'consent_source']

    @action(detail=False, methods=['post'])
    def record(self, request):
        """The single consent-capture endpoint all form flows call (owner|member)."""
        s = ConsentRecordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = get_object_or_404(
            CRMCustomer.objects.filter(
                organization_id__in=self._user_org_ids()
            ),
            pk=s.validated_data['customer'],
        )
        record = consent_service.record_consent(
            customer,
            given=s.validated_data['consent_given'],
            source=s.validated_data['consent_source'],
            text_snapshot=s.validated_data.get('consent_text_snapshot', ''),
            text_version=s.validated_data.get('consent_text_version', 'v1'),
            channels=s.validated_data.get('marketing_channels_allowed', []),
            privacy_notice_version=s.validated_data.get('privacy_notice_version', ''),
        )
        return Response(CRMConsentSerializer(record).data, status=status.HTTP_201_CREATED)


class CRMSegmentViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    queryset = CRMSegment.objects.all()
    serializer_class = CRMSegmentSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]
    search_fields = ['name']

    @action(detail=False, methods=['post'])
    def preview(self, request):
        """Count matching customers for an unsaved rule set."""
        s = SegmentPreviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        org_ids = self._user_org_ids()
        org_id = request.query_params.get('organization') or (org_ids[0] if org_ids else None)
        if org_id is None:
            return Response({'count': 0})
        if str(org_id) not in {str(x) for x in org_ids}:
            return Response(status=status.HTTP_403_FORBIDDEN)
        count = segment_service.preview_count(s.validated_data['filter_rules'], org_id)
        return Response({'count': count})

    @action(detail=True, methods=['get'])
    def customers(self, request, pk=None):
        """Paginated list of customers matching this segment."""
        segment = self.get_object()
        qs = segment_service.evaluate_segment(segment).prefetch_related(_TAG_PREFETCH)
        page = self.paginate_queryset(qs)
        ser = CRMCustomerSerializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @action(detail=True, methods=['get'], url_path='ready-to-engage')
    def ready_to_engage(self, request, pk=None):
        """Segment members WITH valid marketing consent only — the legal-to-act list."""
        segment = self.get_object()
        qs = (
            segment_service.evaluate_segment(segment)
            .filter(marketing_consent_status='given')
            .prefetch_related(_TAG_PREFETCH)
        )
        page = self.paginate_queryset(qs)
        ser = CRMCustomerSerializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)
