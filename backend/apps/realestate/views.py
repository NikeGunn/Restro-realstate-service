"""
Real Estate Vertical Views.
"""
from datetime import timedelta
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Count, Sum, Q

from .models import PropertyListing, Lead, Appointment
from .serializers import (
    PropertyListingSerializer, PropertyListingCreateSerializer, PropertyListingListSerializer,
    LeadSerializer, LeadCreateSerializer, LeadUpdateSerializer, LeadListSerializer,
    AppointmentSerializer, AppointmentCreateSerializer, AppointmentUpdateSerializer,
    PublicPropertyListingSerializer, LeadCaptureSerializer
)
from apps.accounts.models import OrganizationMembership, Organization


class PropertyListingViewSet(viewsets.ModelViewSet):
    """ViewSet for managing property listings."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = PropertyListing.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by listing type
        listing_type = self.request.query_params.get('listing_type')
        if listing_type:
            queryset = queryset.filter(listing_type=listing_type)
        
        # Filter by property type
        property_type = self.request.query_params.get('property_type')
        if property_type:
            queryset = queryset.filter(property_type=property_type)
        
        # Filter by price range
        price_min = self.request.query_params.get('price_min')
        price_max = self.request.query_params.get('price_max')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        if price_max:
            queryset = queryset.filter(price__lte=price_max)
        
        # Filter by bedrooms
        bedrooms_min = self.request.query_params.get('bedrooms_min')
        if bedrooms_min:
            queryset = queryset.filter(bedrooms__gte=bedrooms_min)
        
        # Filter by city
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Filter by featured
        featured = self.request.query_params.get('featured')
        if featured:
            queryset = queryset.filter(is_featured=featured.lower() == 'true')
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(address_line1__icontains=search) |
                Q(city__icontains=search) |
                Q(reference_number__icontains=search)
            )
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PropertyListingListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return PropertyListingCreateSerializer
        return PropertyListingSerializer
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def mark_sold(self, request, pk=None):
        """Mark property as sold/rented."""
        listing = self.get_object()
        if listing.listing_type == PropertyListing.ListingType.RENT:
            listing.status = PropertyListing.Status.RENTED
        else:
            listing.status = PropertyListing.Status.SOLD
        listing.sold_date = timezone.now().date()
        listing.save(update_fields=['status', 'sold_date', 'updated_at'])
        return Response(PropertyListingSerializer(listing).data)
    
    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle featured status."""
        listing = self.get_object()
        listing.is_featured = not listing.is_featured
        listing.save(update_fields=['is_featured', 'updated_at'])
        return Response(PropertyListingSerializer(listing).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get property statistics."""
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        queryset = self.get_queryset().filter(organization_id=org_id)
        
        stats = {
            'total': queryset.count(),
            'by_status': {},
            'by_listing_type': {},
            'by_property_type': {},
            'featured': queryset.filter(is_featured=True).count(),
        }
        
        for s in PropertyListing.Status:
            stats['by_status'][s.value] = queryset.filter(status=s.value).count()
        
        for lt in PropertyListing.ListingType:
            stats['by_listing_type'][lt.value] = queryset.filter(listing_type=lt.value).count()
        
        for pt in PropertyListing.PropertyType:
            count = queryset.filter(property_type=pt.value).count()
            if count > 0:
                stats['by_property_type'][pt.value] = count
        
        return Response(stats)


class LeadViewSet(viewsets.ModelViewSet):
    """ViewSet for managing leads."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = Lead.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by intent
        intent = self.request.query_params.get('intent')
        if intent:
            queryset = queryset.filter(intent=intent)
        
        # Filter by assigned user
        assigned = self.request.query_params.get('assigned')
        if assigned == 'me':
            queryset = queryset.filter(assigned_to=user)
        elif assigned == 'unassigned':
            queryset = queryset.filter(assigned_to__isnull=True)
        
        # Filter by score range
        score_min = self.request.query_params.get('score_min')
        if score_min:
            queryset = queryset.filter(lead_score__gte=score_min)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        return queryset.select_related('assigned_to', 'property_listing')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return LeadListSerializer
        if self.action == 'create':
            return LeadCreateSerializer
        if self.action in ['update', 'partial_update']:
            return LeadUpdateSerializer
        return LeadSerializer
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def mark_contacted(self, request, pk=None):
        """Mark lead as contacted."""
        lead = self.get_object()
        lead.mark_contacted()
        return Response(LeadSerializer(lead).data)
    
    @action(detail=True, methods=['post'])
    def qualify(self, request, pk=None):
        """Mark lead as qualified."""
        lead = self.get_object()
        lead.qualify()
        return Response(LeadSerializer(lead).data)
    
    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Mark lead as converted."""
        lead = self.get_object()
        lead.convert()
        return Response(LeadSerializer(lead).data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign lead to an agent."""
        lead = self.get_object()
        user_id = request.data.get('user_id')
        
        if user_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                agent = User.objects.get(pk=user_id)
                if not OrganizationMembership.objects.filter(
                    user=agent,
                    organization=lead.organization
                ).exists():
                    return Response(
                        {'error': 'User is not a member of this organization.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                lead.assigned_to = agent
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            lead.assigned_to = None
        
        lead.save(update_fields=['assigned_to', 'updated_at'])
        return Response(LeadSerializer(lead).data)
    
    @action(detail=True, methods=['post'])
    def recalculate_score(self, request, pk=None):
        """Recalculate lead score."""
        lead = self.get_object()
        lead.calculate_score()
        return Response(LeadSerializer(lead).data)
    
    @action(detail=False, methods=['get'])
    def hot(self, request):
        """Get hot/high priority leads."""
        queryset = self.get_queryset().filter(
            priority__in=[Lead.Priority.HOT, Lead.Priority.HIGH],
            status__in=[Lead.Status.NEW, Lead.Status.CONTACTED, Lead.Status.QUALIFIED]
        )
        serializer = LeadListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get lead statistics."""
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        queryset = self.get_queryset().filter(
            organization_id=org_id,
            created_at__gte=start_date
        )
        
        stats = {
            'total': queryset.count(),
            'by_status': {},
            'by_priority': {},
            'by_intent': {},
            'by_source': {},
            'conversion_rate': 0,
            'avg_score': 0,
        }
        
        for s in Lead.Status:
            stats['by_status'][s.value] = queryset.filter(status=s.value).count()
        
        for p in Lead.Priority:
            stats['by_priority'][p.value] = queryset.filter(priority=p.value).count()
        
        for i in Lead.IntentType:
            stats['by_intent'][i.value] = queryset.filter(intent=i.value).count()
        
        for src in Lead.Source:
            count = queryset.filter(source=src.value).count()
            if count > 0:
                stats['by_source'][src.value] = count
        
        # Conversion rate
        converted = stats['by_status'].get(Lead.Status.CONVERTED, 0)
        total = stats['total']
        if total > 0:
            stats['conversion_rate'] = round((converted / total) * 100, 1)
        
        # Average score
        from django.db.models import Avg
        avg = queryset.aggregate(avg=Avg('lead_score'))['avg']
        stats['avg_score'] = round(avg, 1) if avg else 0
        
        return Response(stats)


class AppointmentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing appointments."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = Appointment.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date
        date = self.request.query_params.get('date')
        if date:
            queryset = queryset.filter(appointment_date=date)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(appointment_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(appointment_date__lte=end_date)
        
        # Filter by assigned agent
        assigned = self.request.query_params.get('assigned')
        if assigned == 'me':
            queryset = queryset.filter(assigned_agent=user)
        
        # Filter by lead
        lead_id = self.request.query_params.get('lead')
        if lead_id:
            queryset = queryset.filter(lead_id=lead_id)
        
        # Filter by property
        property_id = self.request.query_params.get('property')
        if property_id:
            queryset = queryset.filter(property_listing_id=property_id)
        
        return queryset.select_related('lead', 'property_listing', 'assigned_agent')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return AppointmentCreateSerializer
        if self.action in ['update', 'partial_update']:
            return AppointmentUpdateSerializer
        return AppointmentSerializer
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm appointment."""
        appointment = self.get_object()
        appointment.confirm()
        return Response(AppointmentSerializer(appointment).data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel appointment."""
        appointment = self.get_object()
        reason = request.data.get('reason', '')
        appointment.cancel(reason=reason)
        return Response(AppointmentSerializer(appointment).data)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark appointment as completed."""
        appointment = self.get_object()
        outcome = request.data.get('outcome', '')
        appointment.complete(outcome=outcome)
        return Response(AppointmentSerializer(appointment).data)
    
    @action(detail=True, methods=['post'])
    def no_show(self, request, pk=None):
        """Mark as no-show."""
        appointment = self.get_object()
        appointment.mark_no_show()
        return Response(AppointmentSerializer(appointment).data)
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's appointments."""
        today = timezone.now().date()
        queryset = self.get_queryset().filter(appointment_date=today)
        serializer = AppointmentSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming appointments (next 7 days)."""
        today = timezone.now().date()
        end_date = today + timedelta(days=7)
        queryset = self.get_queryset().filter(
            appointment_date__gte=today,
            appointment_date__lte=end_date,
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]
        )
        serializer = AppointmentSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get appointment statistics."""
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timedelta(days=days)
        
        queryset = self.get_queryset().filter(
            organization_id=org_id,
            created_at__date__gte=start_date
        )
        
        stats = {
            'total': queryset.count(),
            'by_status': {},
            'by_type': {},
            'completion_rate': 0,
            'no_show_rate': 0,
        }
        
        for s in Appointment.Status:
            stats['by_status'][s.value] = queryset.filter(status=s.value).count()
        
        for t in Appointment.AppointmentType:
            count = queryset.filter(appointment_type=t.value).count()
            if count > 0:
                stats['by_type'][t.value] = count
        
        # Rates
        completed = stats['by_status'].get(Appointment.Status.COMPLETED, 0)
        no_show = stats['by_status'].get(Appointment.Status.NO_SHOW, 0)
        finished = completed + no_show + stats['by_status'].get(Appointment.Status.CANCELLED, 0)
        
        if finished > 0:
            stats['completion_rate'] = round((completed / finished) * 100, 1)
            stats['no_show_rate'] = round((no_show / finished) * 100, 1)
        
        return Response(stats)


# Public Widget Endpoints
class PublicPropertySearchView(APIView):
    """Public endpoint for property search (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        widget_key = request.query_params.get('key')
        
        if not widget_key:
            return Response({'error': 'Widget key required.'}, status=400)
        
        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        # Verify it's a real estate org
        if org.business_type != 'real_estate':
            return Response({'error': 'Properties not available for this business type.'}, status=400)
        
        queryset = PropertyListing.objects.filter(
            organization=org,
            is_published=True,
            status=PropertyListing.Status.ACTIVE
        )
        
        # Apply filters
        listing_type = request.query_params.get('listing_type')
        if listing_type:
            queryset = queryset.filter(listing_type=listing_type)
        
        property_type = request.query_params.get('property_type')
        if property_type:
            queryset = queryset.filter(property_type=property_type)
        
        price_min = request.query_params.get('price_min')
        price_max = request.query_params.get('price_max')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        if price_max:
            queryset = queryset.filter(price__lte=price_max)
        
        bedrooms = request.query_params.get('bedrooms')
        if bedrooms:
            queryset = queryset.filter(bedrooms__gte=bedrooms)
        
        city = request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Limit results
        limit = int(request.query_params.get('limit', 20))
        queryset = queryset[:limit]
        
        return Response({
            'count': queryset.count(),
            'properties': PublicPropertyListingSerializer(queryset, many=True).data
        })


class PublicPropertyDetailView(APIView):
    """Public endpoint for single property details (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, property_id):
        widget_key = request.query_params.get('key')
        
        if not widget_key:
            return Response({'error': 'Widget key required.'}, status=400)
        
        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        try:
            listing = PropertyListing.objects.get(
                id=property_id,
                organization=org,
                is_published=True
            )
        except PropertyListing.DoesNotExist:
            return Response({'error': 'Property not found.'}, status=404)
        
        return Response(PublicPropertyListingSerializer(listing).data)


class PublicLeadCaptureView(APIView):
    """Public endpoint for capturing leads (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = LeadCaptureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            org = Organization.objects.get(
                widget_key=data['widget_key'],
                is_active=True
            )
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        # Verify it's a real estate org
        if org.business_type != 'real_estate':
            return Response({'error': 'Lead capture not available for this business type.'}, status=400)
        
        # Get property if specified
        property_listing = None
        if data.get('property_id'):
            try:
                property_listing = PropertyListing.objects.get(
                    id=data['property_id'],
                    organization=org
                )
            except PropertyListing.DoesNotExist:
                pass
        
        # Create lead
        lead = Lead.objects.create(
            organization=org,
            property_listing=property_listing,
            name=data['name'],
            email=data.get('email', ''),
            phone=data['phone'],
            intent=data.get('intent', Lead.IntentType.GENERAL),
            source=Lead.Source.WEBSITE,
            budget_min=data.get('budget_min'),
            budget_max=data.get('budget_max'),
            preferred_areas=data.get('preferred_areas', []),
            timeline=data.get('timeline', ''),
            notes=data.get('message', ''),
        )
        
        # Calculate score
        lead.calculate_score()
        
        return Response({
            'success': True,
            'lead_id': str(lead.id),
            'message': 'Thank you! Our team will contact you shortly.'
        }, status=status.HTTP_201_CREATED)
