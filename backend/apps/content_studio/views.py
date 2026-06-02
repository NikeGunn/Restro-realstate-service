"""
Content Studio API views.

All authenticated mutating endpoints are org-scoped (OrgScopeMixin) and power-plan
gated (ContentStudioPermission). Use-case catalog is read-only to any member.
"""
import uuid

from django.db import transaction, models
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import OrgScopeMixin

from .models import (
    ContentUseCase, BrandKit, ContentGenerationJob, ContentGenerationOutput,
)
from .serializers import (
    ContentUseCaseSerializer, BrandKitSerializer,
    ContentGenerationJobSerializer, ContentGenerationJobCreateSerializer,
    ContentGenerationOutputSerializer,
)
from .permissions import ContentStudioPermission, ContentStudioCatalogPermission

# Use cases that require explicit consent before generation (server-enforced).
_CONSENT_REQUIRED = {'review_testimonial_graphic'}


class ContentUseCaseViewSet(viewsets.ReadOnlyModelViewSet):
    """Seeded catalog of structured use cases — read-only, any member."""
    queryset = ContentUseCase.objects.filter(active=True).select_related('prompt_template')
    serializer_class = ContentUseCaseSerializer
    permission_classes = [IsAuthenticated, ContentStudioCatalogPermission]


class BrandKitViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    """One brand kit per org. GET/PUT/PATCH + logo upload."""
    queryset = BrandKit.objects.select_related('organization').all()
    serializer_class = BrandKitSerializer
    permission_classes = [IsAuthenticated, ContentStudioPermission]
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    @action(detail=True, methods=['post'], url_path='upload-logo')
    def upload_logo(self, request, pk=None):
        brand_kit = self.get_object()
        logo = request.FILES.get('logo')
        if not logo:
            return Response({'logo': 'No file provided.'}, status=400)
        brand_kit.logo = logo
        brand_kit.save(update_fields=['logo', 'updated_at'])
        return Response(self.get_serializer(brand_kit).data)


class ContentGenerationJobViewSet(OrgScopeMixin, viewsets.ModelViewSet):
    """Create (validate + estimate + queue), list, retrieve, cancel, regenerate."""
    queryset = (
        ContentGenerationJob.objects
        .select_related('use_case', 'created_by')
        .prefetch_related('outputs')
        .all()
    )
    permission_classes = [IsAuthenticated, ContentStudioPermission]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return ContentGenerationJobCreateSerializer
        return ContentGenerationJobSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('use_case'):
            qs = qs.filter(use_case_id=params['use_case'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        return qs

    # ── validation helpers ────────────────────────────────────────────
    @staticmethod
    def _validate_payload(use_case, payload):
        """Return an error dict, or None if the payload satisfies the use case."""
        payload = payload or {}
        # Consent gate first — a checkbox-type required field is governed by the
        # explicit gate, not the generic "missing text" check.
        if use_case.use_case_key in _CONSENT_REQUIRED:
            if payload.get('permission_confirmed') is not True:
                return {'permission_confirmed':
                        'You must confirm you have the customer\'s permission to use this review.'}
        missing = []
        for field in (use_case.required_fields or []):
            key = field.get('key')
            if not key or field.get('type') == 'checkbox':
                continue  # checkboxes handled by their own gate, not "missing text"
            val = payload.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(field.get('label') or key)
        if missing:
            return {'input_payload': f'Missing required field(s): {", ".join(missing)}'}
        return None

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = ser.validated_data['organization']
        use_case = ser.validated_data['use_case']

        # Org-scope write check: must be owner of the payload org.
        from apps.accounts.models import OrganizationMembership
        is_owner = OrganizationMembership.objects.filter(
            user=request.user, organization=org,
            role=OrganizationMembership.Role.OWNER,
        ).exists()
        if not is_owner:
            return Response(
                {'detail': 'Only the organization owner can generate content.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        err = self._validate_payload(use_case, ser.validated_data.get('input_payload'))
        if err:
            return Response(err, status=status.HTTP_400_BAD_REQUEST)

        brand_kit = getattr(org, 'brand_kit', None)
        job = ContentGenerationJob.objects.create(
            organization=org,
            created_by=request.user,
            use_case=use_case,
            input_payload=ser.validated_data.get('input_payload') or {},
            aspect=ser.validated_data.get('aspect') or ContentGenerationJob.Aspect.SQUARE,
            output_resolution=ser.validated_data.get('output_resolution') or '1024x1024',
            brand_kit_snapshot=brand_kit.snapshot() if brand_kit else {},
            credits_estimated=use_case.credit_cost,
            idempotency_key=uuid.uuid4().hex,
            status=ContentGenerationJob.Status.QUEUED,
        )
        self._enqueue(job.id)
        out = ContentGenerationJobSerializer(job, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _enqueue(job_id):
        from .tasks import process_generation_job_task
        transaction.on_commit(lambda: process_generation_job_task.delay(str(job_id)))

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in ContentGenerationJob.TERMINAL_STATES:
            return Response(
                {'detail': f'Cannot cancel a {job.status} job.'},
                status=status.HTTP_409_CONFLICT,
            )
        job.status = ContentGenerationJob.Status.CANCELLED
        job.save(update_fields=['status', 'updated_at'])
        return Response(ContentGenerationJobSerializer(
            job, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """New job, same inputs, fresh idempotency key (costs another credit)."""
        src = self.get_object()
        brand_kit = getattr(src.organization, 'brand_kit', None)
        job = ContentGenerationJob.objects.create(
            organization=src.organization,
            created_by=request.user,
            use_case=src.use_case,
            input_payload=src.input_payload,
            aspect=src.aspect,
            output_resolution=src.output_resolution,
            brand_kit_snapshot=brand_kit.snapshot() if brand_kit else {},
            credits_estimated=src.use_case.credit_cost,
            idempotency_key=uuid.uuid4().hex,
            status=ContentGenerationJob.Status.QUEUED,
        )
        self._enqueue(job.id)
        return Response(
            ContentGenerationJobSerializer(job, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ContentGenerationOutputViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only outputs + favorite toggle + download (counts + signed URL).

    Not OrgScopeMixin: ContentGenerationOutput has no direct `organization` FK
    (it's scoped via job.organization), so we filter on that path here. Cross-org
    objects fall out of the queryset → 404, matching the mixin's contract.
    """
    queryset = ContentGenerationOutput.objects.select_related(
        'job', 'job__organization',
    ).all()
    serializer_class = ContentGenerationOutputSerializer
    permission_classes = [IsAuthenticated, ContentStudioPermission]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return self.queryset.none()
        from apps.accounts.models import OrganizationMembership
        org_ids = list(
            OrganizationMembership.objects.filter(user=user)
            .values_list('organization_id', flat=True)
        )
        qs = self.queryset.filter(job__organization_id__in=org_ids)
        if self.request.query_params.get('job'):
            qs = qs.filter(job_id=self.request.query_params['job'])
        if self.request.query_params.get('favorite') == 'true':
            qs = qs.filter(is_favorite=True)
        return qs

    @action(detail=True, methods=['post'])
    def favorite(self, request, pk=None):
        output = self.get_object()
        output.is_favorite = not output.is_favorite
        output.save(update_fields=['is_favorite', 'updated_at'])
        return Response({'id': str(output.id), 'is_favorite': output.is_favorite})

    @action(detail=True, methods=['get', 'post'])
    def download(self, request, pk=None):
        output = self.get_object()
        # Atomic increment — never read-modify-write the counter.
        ContentGenerationOutput.objects.filter(pk=output.pk).update(
            download_count=models.F('download_count') + 1,
        )
        url = output.asset.url if output.asset else None
        request_obj = self.request
        if url and request_obj is not None and url.startswith('/'):
            url = request_obj.build_absolute_uri(url)
        return Response({'id': str(output.id), 'url': url})
