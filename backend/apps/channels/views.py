"""
Channel webhook views.
Handles incoming webhooks from WhatsApp and Instagram.
Includes Manager Number management endpoints.
"""
import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Organization, OrganizationMembership
from .models import WhatsAppConfig, InstagramConfig, WebhookLog, ManagerNumber, TemporaryOverride, ManagerQuery
from .whatsapp_service import WhatsAppService
from .instagram_service import InstagramService
from .serializers import (
    WhatsAppConfigSerializer, 
    InstagramConfigSerializer,
    WebhookLogSerializer,
    ManagerNumberSerializer,
    ManagerNumberCreateSerializer,
    TemporaryOverrideSerializer,
    ManagerQuerySerializer
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):
    """
    WhatsApp webhook endpoint.
    Handles both verification (GET) and incoming messages (POST).
    """
    
    def get(self, request):
        """
        Webhook verification endpoint.
        Meta sends a challenge that must be echoed back.
        """
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        if mode == 'subscribe':
            # Find config with matching verify token
            try:
                config = WhatsAppConfig.objects.get(verify_token=token)
                config.is_verified = True
                config.save()
                logger.info(f"WhatsApp webhook verified for {config.organization.name}")
                return HttpResponse(challenge, content_type='text/plain')
            except WhatsAppConfig.DoesNotExist:
                logger.warning(f"WhatsApp verification failed: invalid token")
                return HttpResponse('Invalid verify token', status=403)
        
        return HttpResponse('Invalid request', status=400)
    
    def post(self, request):
        """
        Handle incoming WhatsApp webhook events.
        """
        webhook_log = None
        try:
            # Get signature from headers
            signature = request.headers.get('X-Hub-Signature-256', '')
            
            # Parse body
            body = json.loads(request.body)
            
            # Find the organization from phone_number_id FIRST
            phone_number_id = None
            config = None
            try:
                entry = body.get('entry', [{}])[0]
                changes = entry.get('changes', [{}])[0]
                value = changes.get('value', {})
                phone_number_id = value.get('metadata', {}).get('phone_number_id')
                
                if phone_number_id:
                    config = WhatsAppConfig.objects.get(
                        phone_number_id=phone_number_id,
                        is_active=True
                    )
            except (IndexError, KeyError) as e:
                logger.error(f"Could not extract phone_number_id from webhook: {e}")
            except WhatsAppConfig.DoesNotExist:
                logger.error(f"❌ CRITICAL: No active WhatsApp config for phone_number_id: {phone_number_id}")
                logger.error(f"Check that WhatsApp config exists and is_active=True in database")
            
            # Log the raw webhook with organization context
            webhook_log = WebhookLog.objects.create(
                source=WebhookLog.Source.WHATSAPP,
                organization=config.organization if config else None,
                headers=dict(request.headers),
                body=body,
                is_processed=False
            )
            logger.info(f"📨 WhatsApp webhook received - Phone ID: {phone_number_id}, Org: {config.organization.name if config else 'Unknown'}")
            
            if config:
                try:
                    service = WhatsAppService(config)
                    
                    # Verify signature in production
                    if signature:
                        if not service.verify_webhook_signature(request.body, signature):
                            error_msg = "WhatsApp webhook signature verification failed"
                            logger.error(f"❌ {error_msg}")
                            webhook_log.error_message = error_msg
                            webhook_log.save()
                            return HttpResponse('Invalid signature', status=401)
                    
                    # Process the webhook
                    success = service.process_webhook(body)
                    
                    if success:
                        webhook_log.is_processed = True
                        webhook_log.save()
                        logger.info(f"✅ WhatsApp webhook processed successfully for {config.organization.name}")
                    else:
                        error_msg = "Webhook processing returned False"
                        logger.error(f"❌ {error_msg}")
                        webhook_log.error_message = error_msg
                        webhook_log.save()
                    
                except Exception as e:
                    error_msg = f"Error in WhatsApp service processing: {str(e)}"
                    logger.exception(f"❌ {error_msg}")
                    if webhook_log:
                        webhook_log.error_message = error_msg
                        webhook_log.save()
            else:
                error_msg = f"No active WhatsApp config found for phone_number_id: {phone_number_id}"
                logger.error(f"❌ {error_msg}")
                if webhook_log:
                    webhook_log.error_message = error_msg
                    webhook_log.save()
            
            # Always return 200 to acknowledge receipt
            return HttpResponse('OK', status=200)
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in WhatsApp webhook: {e}"
            logger.error(f"❌ {error_msg}")
            return HttpResponse('Invalid JSON', status=400)
        except Exception as e:
            error_msg = f"Unexpected error processing WhatsApp webhook: {str(e)}"
            logger.exception(f"❌ {error_msg}")
            if webhook_log:
                webhook_log.error_message = error_msg
                webhook_log.save()
            return HttpResponse('OK', status=200)  # Still return 200 to prevent retries


@method_decorator(csrf_exempt, name='dispatch')
class InstagramWebhookView(View):
    """
    Instagram webhook endpoint.
    Handles both verification (GET) and incoming messages (POST).
    """
    
    def get(self, request):
        """Webhook verification endpoint."""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        if mode == 'subscribe':
            try:
                config = InstagramConfig.objects.get(verify_token=token)
                config.is_verified = True
                config.save()
                logger.info(f"Instagram webhook verified for {config.organization.name}")
                return HttpResponse(challenge, content_type='text/plain')
            except InstagramConfig.DoesNotExist:
                logger.warning("Instagram verification failed: invalid token")
                return HttpResponse('Invalid verify token', status=403)
        
        return HttpResponse('Invalid request', status=400)
    
    def post(self, request):
        """Handle incoming Instagram webhook events."""
        webhook_log = None
        try:
            signature = request.headers.get('X-Hub-Signature-256', '')
            body = json.loads(request.body)
            
            # Find the organization from entry ID FIRST
            # Instagram sends either page_id or instagram_business_id in entry.id
            entry_id = None
            config = None
            try:
                entry = body.get('entry', [{}])[0]
                entry_id = entry.get('id')
                
                if entry_id:
                    # Try to find config by instagram_business_id first (most common)
                    config = InstagramConfig.objects.filter(
                        instagram_business_id=entry_id,
                        is_active=True
                    ).first()
                    
                    # If not found, try by page_id
                    if not config:
                        config = InstagramConfig.objects.filter(
                            page_id=entry_id,
                            is_active=True
                        ).first()
            except (IndexError, KeyError) as e:
                logger.error(f"Could not extract entry_id from Instagram webhook: {e}")
            
            # Log the webhook with organization context
            webhook_log = WebhookLog.objects.create(
                source=WebhookLog.Source.INSTAGRAM,
                organization=config.organization if config else None,
                headers=dict(request.headers),
                body=body,
                is_processed=False
            )
            logger.info(f"📨 Instagram webhook received - Entry ID: {entry_id}, Org: {config.organization.name if config else 'Unknown'}")
            
            if config:
                try:
                    service = InstagramService(config)
                    
                    # Verify signature in production
                    if signature:
                        if not service.verify_webhook_signature(request.body, signature):
                            error_msg = "Instagram webhook signature verification failed"
                            logger.error(f"❌ {error_msg}")
                            webhook_log.error_message = error_msg
                            webhook_log.save()
                            return HttpResponse('Invalid signature', status=401)
                    
                    # Process the webhook
                    success = service.process_webhook(body)
                    
                    if success:
                        webhook_log.is_processed = True
                        webhook_log.save()
                        logger.info(f"✅ Instagram webhook processed successfully for {config.organization.name}")
                    else:
                        error_msg = "Webhook processing returned False"
                        logger.error(f"❌ {error_msg}")
                        webhook_log.error_message = error_msg
                        webhook_log.save()
                        
                except Exception as e:
                    error_msg = f"Error in Instagram service processing: {str(e)}"
                    logger.exception(f"❌ {error_msg}")
                    if webhook_log:
                        webhook_log.error_message = error_msg
                        webhook_log.save()
            else:
                error_msg = f"No active Instagram config found for entry_id: {entry_id}"
                logger.error(f"❌ {error_msg}")
                logger.error(f"   Available configs: {list(InstagramConfig.objects.filter(is_active=True).values_list('instagram_business_id', 'page_id'))}")
                if webhook_log:
                    webhook_log.error_message = error_msg
                    webhook_log.save()
            
            # Always return 200 to acknowledge receipt
            return HttpResponse('OK', status=200)
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in Instagram webhook: {e}"
            logger.error(f"❌ {error_msg}")
            return HttpResponse('Invalid JSON', status=400)
        except Exception as e:
            error_msg = f"Unexpected error processing Instagram webhook: {str(e)}"
            logger.exception(f"❌ {error_msg}")
            if webhook_log:
                webhook_log.error_message = error_msg
                webhook_log.save()
            return HttpResponse('OK', status=200)  # Still return 200 to prevent retries


class WhatsAppConfigViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing WhatsApp configuration.
    """
    serializer_class = WhatsAppConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        return WhatsAppConfig.objects.filter(organization_id__in=org_ids)
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of this organization")
        
        # WhatsApp is available on both Basic and Power plans
        # No plan restriction needed for WhatsApp
        
        config = serializer.save()
        
        # Auto-verify credentials by testing API connection
        self._auto_verify_credentials(config)
    
    def perform_update(self, serializer):
        """Auto-verify credentials when token or phone ID is updated."""
        config = serializer.save()
        
        # Check if critical fields were updated
        if 'access_token' in serializer.validated_data or 'phone_number_id' in serializer.validated_data:
            self._auto_verify_credentials(config)
    
    def _auto_verify_credentials(self, config):
        """
        Automatically verify credentials by testing Meta API connection.
        Sets is_verified=True if successful, False otherwise.
        """
        if not config.access_token or not config.phone_number_id:
            logger.warning(f"Cannot auto-verify WhatsApp config {config.id}: missing credentials")
            return
        
        try:
            import requests
            service = WhatsAppService(config)
            
            url = f"{service.GRAPH_API_URL}/{config.phone_number_id}"
            headers = {"Authorization": f"Bearer {config.access_token}"}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.ok:
                config.is_verified = True
                config.save(update_fields=['is_verified'])
                logger.info(f"✅ Auto-verified WhatsApp config for {config.organization.name}")
            else:
                config.is_verified = False
                config.save(update_fields=['is_verified'])
                logger.warning(f"❌ Auto-verification failed for WhatsApp config {config.id}: {response.text}")
        except Exception as e:
            config.is_verified = False
            config.save(update_fields=['is_verified'])
            logger.error(f"❌ Auto-verification error for WhatsApp config {config.id}: {str(e)}")
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test WhatsApp API connection."""
        config = self.get_object()
        service = WhatsAppService(config)
        
        # Try to get account info
        try:
            import requests
            url = f"{service.GRAPH_API_URL}/{config.phone_number_id}"
            headers = {"Authorization": f"Bearer {config.access_token}"}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.ok:
                return Response({
                    'success': True,
                    'data': response.json()
                })
            else:
                return Response({
                    'success': False,
                    'error': response.text
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def health(self, request, pk=None):
        """
        Comprehensive health check for WhatsApp configuration.
        Returns detailed status of credentials, webhook, and recent activity.
        """
        config = self.get_object()
        service = WhatsAppService(config)
        
        health_data = {
            'organization': config.organization.name,
            'is_active': config.is_active,
            'is_verified': config.is_verified,
            'configuration': {
                'phone_number_id': bool(config.phone_number_id),
                'business_account_id': bool(config.business_account_id),
                'access_token': bool(config.access_token),
            },
            'api_connection': 'unknown',
            'recent_webhooks': {
                'total_24h': 0,
                'processed_24h': 0,
                'failed_24h': 0,
            },
            'issues': []
        }
        
        # Check API connection
        if config.access_token and config.phone_number_id:
            try:
                import requests
                from django.utils import timezone
                
                url = f"{service.GRAPH_API_URL}/{config.phone_number_id}"
                headers = {"Authorization": f"Bearer {config.access_token}"}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.ok:
                    health_data['api_connection'] = 'ok'
                    health_data['phone_info'] = response.json()
                else:
                    health_data['api_connection'] = 'failed'
                    health_data['api_error'] = response.text
                    health_data['issues'].append('Meta API connection failed - access token may be expired')
            except Exception as e:
                health_data['api_connection'] = 'error'
                health_data['api_error'] = str(e)
                health_data['issues'].append(f'API connection error: {str(e)}')
        else:
            health_data['issues'].append('Missing access_token or phone_number_id')
        
        # Check recent webhook activity
        from datetime import timedelta
        from django.utils import timezone
        
        cutoff = timezone.now() - timedelta(hours=24)
        webhooks = WebhookLog.objects.filter(
            source=WebhookLog.Source.WHATSAPP,
            organization=config.organization,
            created_at__gte=cutoff
        )
        
        health_data['recent_webhooks']['total_24h'] = webhooks.count()
        health_data['recent_webhooks']['processed_24h'] = webhooks.filter(is_processed=True).count()
        health_data['recent_webhooks']['failed_24h'] = webhooks.filter(is_processed=False).count()
        
        if health_data['recent_webhooks']['failed_24h'] > 0:
            health_data['issues'].append(f"{health_data['recent_webhooks']['failed_24h']} failed webhooks in last 24h")
        
        # Overall health status
        if not config.is_active:
            health_data['issues'].append('Configuration is inactive')
        
        if not config.is_verified:
            health_data['issues'].append('Webhook not verified with Meta')
        
        from django.conf import settings
        if not settings.OPENAI_API_KEY:
            health_data['issues'].append('CRITICAL: OPENAI_API_KEY not configured - AI will not respond')
        
        health_data['overall_status'] = 'healthy' if len(health_data['issues']) == 0 else 'degraded'
        
        return Response(health_data)


class InstagramConfigViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Instagram configuration.
    """
    serializer_class = InstagramConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        return InstagramConfig.objects.filter(organization_id__in=org_ids)
    
    def perform_create(self, serializer):
        org_id = self.request.data.get('organization')
        if not OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of this organization")
        
        # Instagram requires Power plan
        org = Organization.objects.get(id=org_id)
        if not org.is_power_plan:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Instagram integration requires Power plan")
        
        config = serializer.save()
        
        # Auto-verify credentials by testing API connection
        self._auto_verify_credentials(config)
    
    def perform_update(self, serializer):
        """Auto-verify credentials when token or business ID is updated."""
        config = serializer.save()
        
        # Check if critical fields were updated
        if 'access_token' in serializer.validated_data or 'instagram_business_id' in serializer.validated_data:
            self._auto_verify_credentials(config)
    
    def _auto_verify_credentials(self, config):
        """
        Automatically verify credentials by testing Meta API connection.
        Sets is_verified=True if successful, False otherwise.
        """
        if not config.access_token or not config.instagram_business_id:
            logger.warning(f"Cannot auto-verify Instagram config {config.id}: missing credentials")
            return
        
        try:
            import requests
            
            url = f"https://graph.facebook.com/v18.0/{config.instagram_business_id}"
            params = {
                "fields": "id,username",
                "access_token": config.access_token
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.ok:
                config.is_verified = True
                config.save(update_fields=['is_verified'])
                logger.info(f"✅ Auto-verified Instagram config for {config.organization.name}")
            else:
                config.is_verified = False
                config.save(update_fields=['is_verified'])
                logger.warning(f"❌ Auto-verification failed for Instagram config {config.id}: {response.text}")
        except Exception as e:
            config.is_verified = False
            config.save(update_fields=['is_verified'])
            logger.error(f"❌ Auto-verification error for Instagram config {config.id}: {str(e)}")
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test Instagram API connection."""
        config = self.get_object()
        
        try:
            import requests
            url = f"https://graph.facebook.com/v18.0/{config.instagram_business_id}"
            params = {
                "fields": "id,username",
                "access_token": config.access_token
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.ok:
                return Response({
                    'success': True,
                    'data': response.json()
                })
            else:
                return Response({
                    'success': False,
                    'error': response.text
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def health(self, request, pk=None):
        """
        Comprehensive health check for Instagram configuration.
        Returns detailed status of credentials, webhook, and recent activity.
        """
        config = self.get_object()
        
        health_data = {
            'organization': config.organization.name,
            'is_active': config.is_active,
            'is_verified': config.is_verified,
            'configuration': {
                'instagram_business_id': bool(config.instagram_business_id),
                'page_id': bool(config.page_id),
                'access_token': bool(config.access_token),
            },
            'api_connection': 'unknown',
            'recent_webhooks': {
                'total_24h': 0,
                'processed_24h': 0,
                'failed_24h': 0,
            },
            'issues': []
        }
        
        # Check API connection
        if config.access_token and config.instagram_business_id:
            try:
                import requests
                from django.utils import timezone
                
                url = f"https://graph.facebook.com/v18.0/{config.instagram_business_id}"
                params = {
                    "fields": "id,username",
                    "access_token": config.access_token
                }
                response = requests.get(url, params=params, timeout=10)
                
                if response.ok:
                    health_data['api_connection'] = 'ok'
                    health_data['instagram_info'] = response.json()
                else:
                    health_data['api_connection'] = 'failed'
                    health_data['api_error'] = response.text
                    health_data['issues'].append('Meta API connection failed - access token may be expired')
            except Exception as e:
                health_data['api_connection'] = 'error'
                health_data['api_error'] = str(e)
                health_data['issues'].append(f'API connection error: {str(e)}')
        else:
            health_data['issues'].append('Missing access_token or instagram_business_id')
        
        # Check recent webhook activity
        from datetime import timedelta
        from django.utils import timezone
        
        cutoff = timezone.now() - timedelta(hours=24)
        webhooks = WebhookLog.objects.filter(
            source=WebhookLog.Source.INSTAGRAM,
            organization=config.organization,
            created_at__gte=cutoff
        )
        
        health_data['recent_webhooks']['total_24h'] = webhooks.count()
        health_data['recent_webhooks']['processed_24h'] = webhooks.filter(is_processed=True).count()
        health_data['recent_webhooks']['failed_24h'] = webhooks.filter(is_processed=False).count()
        
        if health_data['recent_webhooks']['failed_24h'] > 0:
            health_data['issues'].append(f"{health_data['recent_webhooks']['failed_24h']} failed webhooks in last 24h")
        
        # Overall health status
        if not config.is_active:
            health_data['issues'].append('Configuration is inactive')
        
        if not config.is_verified:
            health_data['issues'].append('Webhook not verified with Meta')
        
        # Check if organization has Power plan
        if not config.organization.is_power_plan:
            health_data['issues'].append('Organization does not have Power plan - Instagram will not work')
        
        from django.conf import settings
        if not settings.OPENAI_API_KEY:
            health_data['issues'].append('CRITICAL: OPENAI_API_KEY not configured - AI will not respond')
        
        health_data['overall_status'] = 'healthy' if len(health_data['issues']) == 0 else 'degraded'
        
        return Response(health_data)


class WebhookLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing webhook logs (debugging).
    """
    serializer_class = WebhookLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = WebhookLog.objects.filter(organization_id__in=org_ids)
        
        source = self.request.query_params.get('source')
        if source:
            queryset = queryset.filter(source=source)
        
        return queryset[:100]  # Limit to last 100 logs


class ManagerNumberViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Manager WhatsApp Numbers.
    Managers can receive commands via WhatsApp to control the chatbot.
    Uses existing WhatsApp configuration credentials automatically.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ManagerNumberCreateSerializer
        return ManagerNumberSerializer
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = ManagerNumber.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization if provided
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        return queryset.order_by('-is_active', 'name')
    
    def create(self, request, *args, **kwargs):
        """
        Create manager number and return full serialized object.
        Override to return ManagerNumberSerializer response instead of
        ManagerNumberCreateSerializer (which doesn't include id).
        """
        create_serializer = self.get_serializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        self.perform_create(create_serializer)
        
        # Re-serialize with full serializer to include id and all fields
        instance = create_serializer.instance
        response_serializer = ManagerNumberSerializer(instance, context={'request': request})
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def perform_create(self, serializer):
        """Create manager number with permission check."""
        org_id = self.request.data.get('organization')
        
        # Check membership
        membership = OrganizationMembership.objects.filter(
            user=self.request.user,
            organization_id=org_id
        ).first()
        
        if not membership:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of this organization")
        
        # Only owners and managers can add manager numbers
        if membership.role not in ['owner', 'manager']:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only owners and managers can add manager numbers")
        
        serializer.save()
        logger.info(f"✅ Manager number added: {self.request.data.get('phone_number')} for org {org_id}")
    
    def perform_destroy(self, instance):
        """Log deletion of manager number."""
        logger.info(f"🗑️ Manager number removed: {instance.phone_number} ({instance.name})")
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def test_message(self, request, pk=None):
        """
        Send a test message to verify the manager number is working.
        Uses the organization's WhatsApp configuration.
        """
        manager = self.get_object()
        
        try:
            whatsapp_config = WhatsAppConfig.objects.get(
                organization=manager.organization,
                is_active=True
            )
        except WhatsAppConfig.DoesNotExist:
            return Response({
                'success': False,
                'error': 'WhatsApp is not configured or not active for this organization'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            service = WhatsAppService(whatsapp_config)
            message_id = service.send_message(
                manager.phone_number,
                f"🤖 Test Message from {manager.organization.name}\n\n"
                f"Hello {manager.name}! This is a test message to confirm your manager number is configured correctly.\n\n"
                f"You can now send commands to control the chatbot. Send 'help' to see available commands."
            )
            
            if message_id:
                return Response({
                    'success': True,
                    'message': 'Test message sent successfully',
                    'message_id': message_id
                })
            else:
                return Response({
                    'success': False,
                    'error': 'Failed to send message - check WhatsApp configuration'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.exception(f"Error sending test message to manager: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def check_whatsapp_ready(self, request):
        """
        Check if WhatsApp is configured and ready for an organization.
        Returns whether manager numbers can be added.
        """
        org_id = request.query_params.get('organization')
        if not org_id:
            return Response({
                'ready': False,
                'error': 'organization parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            config = WhatsAppConfig.objects.get(
                organization_id=org_id,
                is_active=True
            )
            return Response({
                'ready': True,
                'whatsapp_verified': config.is_verified,
                'message': 'WhatsApp is configured. You can add manager numbers.'
            })
        except WhatsAppConfig.DoesNotExist:
            return Response({
                'ready': False,
                'error': 'Please configure and activate WhatsApp first before adding manager numbers.'
            })


class TemporaryOverrideViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and managing Temporary Overrides.
    Overrides are typically created by managers via WhatsApp,
    but can also be viewed/cancelled from the dashboard.
    """
    serializer_class = TemporaryOverrideSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = TemporaryOverride.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by active status
        active_only = self.request.query_params.get('active')
        if active_only == 'true':
            from django.utils import timezone
            queryset = queryset.filter(
                is_active=True,
                expires_at__gt=timezone.now()
            )
        
        return queryset.order_by('-priority', '-created_at')
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate an override early."""
        override = self.get_object()
        override.is_active = False
        override.save()
        
        return Response({
            'success': True,
            'message': 'Override deactivated'
        })
    
    @action(detail=False, methods=['post'])
    def deactivate_all(self, request):
        """Deactivate all active overrides for an organization."""
        org_id = request.data.get('organization')
        if not org_id:
            return Response({
                'error': 'organization parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permission
        if not OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Not a member of this organization")
        
        from django.utils import timezone
        count = TemporaryOverride.objects.filter(
            organization_id=org_id,
            is_active=True,
            expires_at__gt=timezone.now()
        ).update(is_active=False)
        
        return Response({
            'success': True,
            'deactivated_count': count,
            'message': f'Deactivated {count} override(s)'
        })


class ManagerQueryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Manager Queries (read-only from dashboard).
    Queries are created automatically when AI needs manager input.
    """
    serializer_class = ManagerQuerySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        org_ids = OrganizationMembership.objects.filter(
            user=user
        ).values_list('organization_id', flat=True)
        
        queryset = ManagerQuery.objects.filter(organization_id__in=org_ids)
        
        # Filter by organization
        org_id = self.request.query_params.get('organization')
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')[:100]
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get all pending queries."""
        org_id = request.query_params.get('organization')
        
        queryset = self.get_queryset().filter(status=ManagerQuery.Status.PENDING)
        
        if org_id:
            queryset = queryset.filter(organization_id=org_id)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
