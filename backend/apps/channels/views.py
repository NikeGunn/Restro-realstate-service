"""
Channel webhook views.
Handles incoming webhooks from WhatsApp and Instagram.
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
from .models import WhatsAppConfig, InstagramConfig, WebhookLog
from .whatsapp_service import WhatsAppService
from .instagram_service import InstagramService
from .serializers import (
    WhatsAppConfigSerializer, 
    InstagramConfigSerializer,
    WebhookLogSerializer
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
        try:
            signature = request.headers.get('X-Hub-Signature-256', '')
            body = json.loads(request.body)
            
            # Log the webhook
            WebhookLog.objects.create(
                source=WebhookLog.Source.INSTAGRAM,
                headers=dict(request.headers),
                body=body
            )
            
            # Find organization from page ID
            page_id = None
            try:
                entry = body.get('entry', [{}])[0]
                page_id = entry.get('id')
            except (IndexError, KeyError):
                pass
            
            if page_id:
                try:
                    config = InstagramConfig.objects.get(
                        page_id=page_id,
                        is_active=True
                    )
                    service = InstagramService(config)
                    
                    if signature:
                        if not service.verify_webhook_signature(request.body, signature):
                            logger.warning("Instagram webhook signature verification failed")
                            return HttpResponse('Invalid signature', status=401)
                    
                    service.process_webhook(body)
                    
                except InstagramConfig.DoesNotExist:
                    logger.warning(f"No Instagram config for page_id: {page_id}")
            
            return HttpResponse('OK', status=200)
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in Instagram webhook")
            return HttpResponse('Invalid JSON', status=400)
        except Exception as e:
            logger.exception(f"Error processing Instagram webhook: {e}")
            return HttpResponse('OK', status=200)


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
        
        serializer.save()
    
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
        
        serializer.save()
    
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
