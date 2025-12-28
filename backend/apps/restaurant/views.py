"""
Restaurant Vertical Views.
"""
from datetime import datetime, timedelta
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Sum

from .models import (
    MenuCategory, MenuItem, OpeningHours, DailySpecial,
    Booking, BookingSettings
)
from .serializers import (
    MenuCategorySerializer, MenuCategoryListSerializer, MenuCategoryCreateSerializer,
    MenuItemSerializer, MenuItemCreateSerializer,
    OpeningHoursSerializer, OpeningHoursCreateSerializer,
    DailySpecialSerializer, DailySpecialCreateSerializer,
    BookingSerializer, BookingCreateSerializer, BookingUpdateSerializer,
    BookingSettingsSerializer, BookingSettingsCreateSerializer,
    PublicMenuCategorySerializer, PublicDailySpecialSerializer,
    PublicOpeningHoursSerializer, BookingAvailabilitySerializer, BookingSlotSerializer
)
from apps.accounts.models import OrganizationMembership, Organization


class MenuCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing menu categories."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = MenuCategory.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Filter by active status
        active = self.request.query_params.get('active')
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == 'true')
        
        return queryset.prefetch_related('items')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return MenuCategoryCreateSerializer
        return MenuCategorySerializer
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        serializer.save()
    
    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Reorder categories."""
        items = request.data.get('items', [])
        for item in items:
            MenuCategory.objects.filter(pk=item['id']).update(display_order=item['order'])
        return Response({'status': 'Categories reordered.'})


class MenuItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing menu items."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = MenuItem.objects.filter(
            category__organization_id__in=org_ids
        )
        
        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(category__organization_id=org_id)
        
        # Filter by active/available
        active = self.request.query_params.get('active')
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == 'true')
        
        available = self.request.query_params.get('available')
        if available is not None:
            queryset = queryset.filter(is_available=available.lower() == 'true')
        
        return queryset.select_related('category')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return MenuItemCreateSerializer
        return MenuItemSerializer
    
    def perform_create(self, serializer):
        category_id = self.request.data.get('category')
        try:
            category = MenuCategory.objects.get(pk=category_id)
        except MenuCategory.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Category not found.')
        
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=category.organization_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        
        serializer.save()
    
    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Reorder items within a category."""
        items = request.data.get('items', [])
        for item in items:
            MenuItem.objects.filter(pk=item['id']).update(display_order=item['order'])
        return Response({'status': 'Items reordered.'})
    
    @action(detail=True, methods=['post'])
    def toggle_availability(self, request, pk=None):
        """Toggle item availability."""
        item = self.get_object()
        item.is_available = not item.is_available
        item.save(update_fields=['is_available', 'updated_at'])
        return Response(MenuItemSerializer(item).data)


class OpeningHoursViewSet(viewsets.ModelViewSet):
    """ViewSet for managing opening hours."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = OpeningHours.objects.filter(
            location__organization_id__in=org_ids
        )
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        return queryset.select_related('location')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return OpeningHoursCreateSerializer
        return OpeningHoursSerializer
    
    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update opening hours for a location."""
        location_id = request.data.get('location')
        hours = request.data.get('hours', [])
        
        if not location_id:
            return Response({'error': 'Location ID required.'}, status=400)
        
        for hour_data in hours:
            OpeningHours.objects.update_or_create(
                location_id=location_id,
                day_of_week=hour_data['day_of_week'],
                defaults={
                    'open_time': hour_data.get('open_time'),
                    'close_time': hour_data.get('close_time'),
                    'open_time_2': hour_data.get('open_time_2'),
                    'close_time_2': hour_data.get('close_time_2'),
                    'is_closed': hour_data.get('is_closed', False),
                }
            )
        
        return Response({'status': 'Opening hours updated.'})


class DailySpecialViewSet(viewsets.ModelViewSet):
    """ViewSet for managing daily specials."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = DailySpecial.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        # Filter by active
        active = self.request.query_params.get('active')
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == 'true')
        
        # Filter for today's specials
        today_only = self.request.query_params.get('today')
        if today_only:
            today = timezone.now().date()
            queryset = queryset.filter(
                start_date__lte=today,
                end_date__gte=today,
                is_active=True
            )
        
        return queryset
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DailySpecialCreateSerializer
        return DailySpecialSerializer
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this organization.')
        serializer.save()


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for managing restaurant bookings."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = Booking.objects.filter(organization_id__in=org_ids)
        
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
            queryset = queryset.filter(booking_date=date)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(booking_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(booking_date__lte=end_date)
        
        # Filter by source
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)
        
        return queryset.select_related('location', 'confirmed_by')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        if self.action in ['update', 'partial_update']:
            return BookingUpdateSerializer
        return BookingSerializer
    
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
        """Confirm a booking."""
        booking = self.get_object()
        if booking.status != Booking.Status.PENDING:
            return Response(
                {'error': 'Only pending bookings can be confirmed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        booking.confirm(user=request.user)
        return Response(BookingSerializer(booking).data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking."""
        booking = self.get_object()
        if booking.status in [Booking.Status.CANCELLED, Booking.Status.COMPLETED]:
            return Response(
                {'error': 'This booking cannot be cancelled.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        reason = request.data.get('reason', '')
        booking.cancel(reason=reason)
        return Response(BookingSerializer(booking).data)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark booking as completed (guest arrived)."""
        booking = self.get_object()
        if booking.status != Booking.Status.CONFIRMED:
            return Response(
                {'error': 'Only confirmed bookings can be marked as completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        booking.complete()
        return Response(BookingSerializer(booking).data)
    
    @action(detail=True, methods=['post'])
    def no_show(self, request, pk=None):
        """Mark booking as no-show."""
        booking = self.get_object()
        if booking.status != Booking.Status.CONFIRMED:
            return Response(
                {'error': 'Only confirmed bookings can be marked as no-show.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        booking.no_show()
        return Response(BookingSerializer(booking).data)
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's bookings."""
        today = timezone.now().date()
        queryset = self.get_queryset().filter(booking_date=today)
        serializer = BookingSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming bookings (next 7 days)."""
        today = timezone.now().date()
        end_date = today + timedelta(days=7)
        queryset = self.get_queryset().filter(
            booking_date__gte=today,
            booking_date__lte=end_date,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
        )
        serializer = BookingSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get booking statistics."""
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({'error': 'Organization ID required.'}, status=400)
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timedelta(days=days)
        
        bookings = self.get_queryset().filter(
            organization_id=org_id,
            created_at__date__gte=start_date
        )
        
        stats = {
            'total': bookings.count(),
            'by_status': {},
            'by_source': {},
            'total_guests': bookings.aggregate(total=Sum('party_size'))['total'] or 0,
        }
        
        for s in Booking.Status:
            stats['by_status'][s.value] = bookings.filter(status=s.value).count()
        
        for src in Booking.Source:
            stats['by_source'][src.value] = bookings.filter(source=src.value).count()
        
        return Response(stats)


class BookingSettingsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing booking settings."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = BookingSettings.objects.filter(
            location__organization_id__in=org_ids
        )
        
        location_id = self.request.query_params.get('location')
        if location_id:
            queryset = queryset.filter(location_id=location_id)
        
        return queryset.select_related('location')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return BookingSettingsCreateSerializer
        return BookingSettingsSerializer


class BookingAvailabilityView(APIView):
    """Check booking availability for a date."""
    permission_classes = [permissions.AllowAny]  # Public endpoint for widget
    
    def get(self, request):
        location_id = request.query_params.get('location')
        date_str = request.query_params.get('date')
        party_size = int(request.query_params.get('party_size', 2))
        
        if not location_id or not date_str:
            return Response(
                {'error': 'location and date are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get opening hours for the day
        day_of_week = date.weekday()
        try:
            hours = OpeningHours.objects.get(
                location_id=location_id,
                day_of_week=day_of_week
            )
        except OpeningHours.DoesNotExist:
            return Response({'available_slots': [], 'message': 'No opening hours configured.'})
        
        if hours.is_closed:
            return Response({'available_slots': [], 'message': 'Closed on this day.'})
        
        # Get booking settings
        try:
            settings = BookingSettings.objects.get(location_id=location_id)
        except BookingSettings.DoesNotExist:
            settings = None
        
        # Generate time slots
        slots = []
        slot_duration = settings.slot_duration_minutes if settings else 30
        max_bookings = settings.max_bookings_per_slot if settings else 5
        
        current_time = datetime.combine(date, hours.open_time)
        end_time = datetime.combine(date, hours.close_time)
        
        # Get existing bookings for this date
        existing_bookings = Booking.objects.filter(
            location_id=location_id,
            booking_date=date,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
        )
        
        while current_time < end_time:
            slot_time = current_time.time()
            
            # Count bookings for this slot
            bookings_at_slot = existing_bookings.filter(
                booking_time=slot_time
            ).count()
            
            available = bookings_at_slot < max_bookings
            
            # Check if slot is in the past
            if date == timezone.now().date():
                min_hours = settings.min_advance_hours if settings else 2
                min_time = (timezone.now() + timedelta(hours=min_hours)).time()
                if slot_time < min_time:
                    available = False
            
            slots.append({
                'time': slot_time.strftime('%H:%M'),
                'available': available,
                'remaining': max_bookings - bookings_at_slot if available else 0
            })
            
            current_time += timedelta(minutes=slot_duration)
        
        return Response({
            'date': date_str,
            'day': hours.get_day_of_week_display(),
            'opening_time': hours.open_time.strftime('%H:%M'),
            'closing_time': hours.close_time.strftime('%H:%M'),
            'available_slots': slots
        })


# Public Widget Endpoints
class PublicMenuView(APIView):
    """Public endpoint for getting menu (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        widget_key = request.query_params.get('key')
        location_id = request.query_params.get('location')
        
        if not widget_key:
            return Response({'error': 'Widget key required.'}, status=400)
        
        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        # Verify it's a restaurant
        if org.business_type != 'restaurant':
            return Response({'error': 'Menu not available for this business type.'}, status=400)
        
        # Get categories with items
        categories = MenuCategory.objects.filter(
            organization=org,
            is_active=True
        ).prefetch_related('items')
        
        # Filter by location if specified
        if location_id:
            categories = categories.filter(
                models.Q(location_id=location_id) | models.Q(location__isnull=True)
            )
        
        return Response({
            'business_name': org.name,
            'categories': PublicMenuCategorySerializer(categories, many=True).data
        })


class PublicSpecialsView(APIView):
    """Public endpoint for getting today's specials (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        widget_key = request.query_params.get('key')
        location_id = request.query_params.get('location')
        
        if not widget_key:
            return Response({'error': 'Widget key required.'}, status=400)
        
        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        today = timezone.now().date()
        specials = DailySpecial.objects.filter(
            organization=org,
            start_date__lte=today,
            end_date__gte=today,
            is_active=True
        )
        
        if location_id:
            specials = specials.filter(
                models.Q(location_id=location_id) | models.Q(location__isnull=True)
            )
        
        # Filter by recurring days
        available_specials = [s for s in specials if s.is_available_today]
        
        return Response({
            'date': today.isoformat(),
            'specials': PublicDailySpecialSerializer(available_specials, many=True).data
        })


class PublicHoursView(APIView):
    """Public endpoint for getting opening hours (widget use)."""
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        widget_key = request.query_params.get('key')
        location_id = request.query_params.get('location')
        
        if not widget_key:
            return Response({'error': 'Widget key required.'}, status=400)
        
        try:
            org = Organization.objects.get(widget_key=widget_key, is_active=True)
        except Organization.DoesNotExist:
            return Response({'error': 'Invalid widget key.'}, status=404)
        
        if not location_id:
            # Get primary location
            from apps.accounts.models import Location
            location = Location.objects.filter(
                organization=org,
                is_primary=True
            ).first()
            if not location:
                location = Location.objects.filter(organization=org).first()
            if location:
                location_id = location.id
        
        hours = OpeningHours.objects.filter(location_id=location_id).order_by('day_of_week')
        
        return Response({
            'hours': PublicOpeningHoursSerializer(hours, many=True).data
        })
