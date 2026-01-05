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
        try:
            # Get signature from headers
            signature = request.headers.get('X-Hub-Signature-256', '')
            
            # Parse body
            body = json.loads(request.body)
            
            # Log the raw webhook
            WebhookLog.objects.create(
                source=WebhookLog.Source.WHATSAPP,
                headers=dict(request.headers),
                body=body
            )
            
            # Find the organization from phone_number_id
            phone_number_id = None
            try:
                entry = body.get('entry', [{}])[0]
                changes = entry.get('changes', [{}])[0]
                value = changes.get('value', {})
                phone_number_id = value.get('metadata', {}).get('phone_number_id')
            except (IndexError, KeyError):
                pass
            
            if phone_number_id:
                try:
                    config = WhatsAppConfig.objects.get(
                        phone_number_id=phone_number_id,
                        is_active=True
                    )
                    service = WhatsAppService(config)
                    
                    # Verify signature in production
                    if signature:
                        if not service.verify_webhook_signature(request.body, signature):
                            logger.warning("WhatsApp webhook signature verification failed")
                            return HttpResponse('Invalid signature', status=401)
                    
                    # Process the webhook
                    service.process_webhook(body)
                    
                except WhatsAppConfig.DoesNotExist:
                    logger.warning(f"No WhatsApp config for phone_number_id: {phone_number_id}")
            
            # Always return 200 to acknowledge receipt
            return HttpResponse('OK', status=200)
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in WhatsApp webhook")
            return HttpResponse('Invalid JSON', status=400)
        except Exception as e:
            logger.exception(f"Error processing WhatsApp webhook: {e}")
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
        
        # Check for Power plan (WhatsApp requires Power plan)
        org = Organization.objects.get(id=org_id)
        if not org.is_power_plan:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("WhatsApp integration requires Power plan")
        
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
