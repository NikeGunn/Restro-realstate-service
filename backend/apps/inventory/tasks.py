"""
Celery tasks for inventory (Plane B).

These tasks NEVER reach the public chatbot. WhatsApp messages produced
here are addressed to OWNER phone numbers, not to customer conversations.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Excel imports (sales / purchase)
# ──────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_excel_import_task(self, import_id: str, import_type: str):
    """Parses + commits a SalesImport or SupplierImport in the background."""
    from .models import SalesImport, SupplierImport
    from .services.excel_parser import ExcelParser
    from .services.stock_engine import StockEngine

    Model = SalesImport if import_type == 'sales' else SupplierImport
    try:
        instance = Model.objects.select_related('organization').get(pk=import_id)
    except Model.DoesNotExist:
        logger.warning('process_excel_import_task: %s %s not found', import_type, import_id)
        return

    parser_kind = 'sales' if import_type == 'sales' else 'purchase'
    parser = ExcelParser(
        file_path=instance.import_file.path,
        import_type=parser_kind,
        organization=instance.organization,
        location=getattr(instance, 'location', None),
    )

    try:
        parsed = parser.parse(column_overrides=instance.column_map or None)
    except Exception as e:
        instance.status = instance.Status.FAILED
        instance.error_log = [{'row': 0, 'column': '', 'message': f'Parse failed: {e}'}]
        instance.save(update_fields=['status', 'error_log', 'updated_at'])
        return

    total = parsed['total_rows'] or 1
    err_ratio = Decimal(parsed['error_rows']) / Decimal(total)
    threshold = Decimal('0.30')
    if err_ratio > threshold:
        instance.status = instance.Status.FAILED
        instance.row_count = parsed['total_rows']
        instance.error_count = parsed['error_rows']
        instance.error_log = parsed['errors']
        instance.summary = {
            'aborted': True,
            'reason': f'Error rate {err_ratio:.2%} exceeded 30% threshold.',
        }
        instance.save(update_fields=[
            'status', 'row_count', 'error_count', 'error_log', 'summary', 'updated_at',
        ])
        return

    # Resolve items + apply movements (only valid rows).
    valid_rows = []
    skipped = list(parsed['errors'])
    for r in parsed['rows']:
        if r['errors']:
            continue
        item = parser.resolve_item({'sku': r['sku'], 'name': r['name']})
        if not item:
            skipped.append({
                'row': r['row_num'], 'column': 'name/sku',
                'message': f"Could not resolve item '{r['name'] or r['sku']}'.",
            })
            continue
        valid_rows.append({
            'item': item,
            'quantity': r['quantity'],
            'unit_cost': r['unit_cost'],
            'movement_date': r['movement_date'],
        })

    engine = StockEngine(
        organization=instance.organization,
        location=getattr(instance, 'location', None),
        performed_by=instance.created_by,
    )
    try:
        if import_type == 'sales':
            summary = engine.apply_sales_import(instance, valid_rows)
        else:
            summary = engine.apply_purchase_import(instance, valid_rows)
    except Exception as e:
        instance.status = instance.Status.FAILED
        instance.error_log = (parsed['errors'] or []) + [
            {'row': 0, 'column': '', 'message': f'Apply failed: {e}'},
        ]
        instance.save(update_fields=['status', 'error_log', 'updated_at'])
        raise self.retry(exc=e)

    instance.status = instance.Status.COMPLETED
    instance.row_count = parsed['total_rows']
    instance.processed_count = len(valid_rows)
    instance.error_count = len(skipped)
    instance.error_log = skipped
    instance.summary = summary
    instance.imported_at = timezone.now()
    instance.save(update_fields=[
        'status', 'row_count', 'processed_count', 'error_count',
        'error_log', 'summary', 'imported_at', 'updated_at',
    ])


# ──────────────────────────────────────────────────────────────────────
# Stock alerts
# ──────────────────────────────────────────────────────────────────────
@shared_task
def check_low_stock_task(item_id: str):
    """
    Async low-stock check. Creates StockAlert if no open one exists,
    then queues a WhatsApp notification.
    """
    from .models import InventoryItem, StockAlert
    from django.conf import settings

    try:
        item = InventoryItem.objects.select_related('organization').get(pk=item_id)
    except InventoryItem.DoesNotExist:
        return

    cooldown_h = settings.INVENTORY_SETTINGS.get('LOW_STOCK_ALERT_COOLDOWN_HOURS', 24)
    cutoff = timezone.now() - timedelta(hours=cooldown_h)

    if item.reorder_level > 0 and item.current_stock <= item.reorder_level:
        recent = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.LOW_STOCK,
            triggered_at__gte=cutoff,
        ).exists()
        if not recent:
            alert = StockAlert.objects.create(
                organization=item.organization,
                location=item.location,
                item=item,
                alert_type=StockAlert.AlertType.LOW_STOCK,
                message=(
                    f'{item.name} ({item.sku}) at {item.current_stock} {item.unit}, '
                    f'below reorder level of {item.reorder_level}.'
                ),
            )
            send_stock_alert_whatsapp_task.delay(str(alert.id))

    if item.current_stock < 0:
        already_open = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
            is_resolved=False,
        ).exists()
        if not already_open:
            StockAlert.objects.create(
                organization=item.organization,
                location=item.location,
                item=item,
                alert_type=StockAlert.AlertType.NEGATIVE_STOCK,
                message=f'{item.name} has negative stock: {item.current_stock} {item.unit}.',
            )


@shared_task
def send_stock_alert_whatsapp_task(alert_id: str):
    """Sends an alert to the OWNER's WhatsApp number, not a customer conv."""
    from .models import StockAlert
    from .services.ai_engine import InventoryAIEngine
    from apps.accounts.models import OrganizationMembership

    try:
        alert = StockAlert.objects.select_related('item', 'item__organization').get(pk=alert_id)
    except StockAlert.DoesNotExist:
        return
    if alert.whatsapp_sent:
        return

    org = alert.item.organization
    owner_membership = OrganizationMembership.objects.filter(
        organization=org, role=OrganizationMembership.Role.OWNER,
    ).select_related('user').first()
    if not owner_membership:
        logger.info('No owner found for org %s — skipping WhatsApp alert.', org.id)
        return
    owner = owner_membership.user
    phone = (
        getattr(owner, 'phone', None)
        or getattr(owner, 'whatsapp_number', None)
        or getattr(org, 'phone', None)
    )
    if not phone:
        logger.info('Owner phone not set for org %s — skipping WhatsApp alert.', org.id)
        return

    try:
        from apps.channels.whatsapp_service import WhatsAppService
        service = WhatsAppService.get_for_organization(org)
        if service is None:
            logger.info('No WhatsApp config for org %s — skipping alert.', org.id)
            return
        message = InventoryAIEngine().generate_stock_alert_message(alert.item)
        service.send_message(to=phone, text=message)
    except Exception:
        logger.exception('Failed to send stock alert WhatsApp for alert %s', alert_id)
        return

    StockAlert.objects.filter(pk=alert_id).update(
        whatsapp_sent=True, whatsapp_sent_at=timezone.now(),
    )


# ──────────────────────────────────────────────────────────────────────
# Daily digest
# ──────────────────────────────────────────────────────────────────────
@shared_task
def generate_daily_inventory_summary_task(organization_id: str = None):
    """Sends a daily digest to each org's owner via WhatsApp."""
    from apps.accounts.models import Organization, OrganizationMembership
    from .models import InventoryItem, StockMovement, StockAlert
    from .services.ai_engine import InventoryAIEngine

    qs = Organization.objects.all()
    if organization_id:
        qs = qs.filter(pk=organization_id)

    yesterday = timezone.now().date() - timedelta(days=1)
    for org in qs:
        items = InventoryItem.objects.filter(organization=org, is_active=True)
        critical_count = sum(
            1 for i in items.values('current_stock', 'reorder_level')
            if i['reorder_level'] > 0 and i['current_stock'] <= i['reorder_level']
        )
        movements_yesterday = StockMovement.objects.filter(
            organization=org, movement_date=yesterday, is_reversed=False,
        )
        in_total = sum(
            (m['quantity'] for m in movements_yesterday.values('quantity') if m['quantity'] > 0),
            Decimal('0'),
        )
        out_total = -sum(
            (m['quantity'] for m in movements_yesterday.values('quantity') if m['quantity'] < 0),
            Decimal('0'),
        )
        open_alerts = StockAlert.objects.filter(organization=org, is_resolved=False).count()

        summary_lines = [
            f'• Active items: {items.count()}',
            f'• Items at/below reorder level: {critical_count}',
            f'• Yesterday — stock in: {in_total}, stock out: {out_total}',
            f'• Open alerts: {open_alerts}',
        ]
        message = InventoryAIEngine().generate_daily_summary(org, summary_lines)

        owner = OrganizationMembership.objects.filter(
            organization=org, role=OrganizationMembership.Role.OWNER,
        ).select_related('user').first()
        if not owner:
            continue
        phone = (
            getattr(owner.user, 'phone', None)
            or getattr(owner.user, 'whatsapp_number', None)
            or getattr(org, 'phone', None)
        )
        if not phone:
            continue
        try:
            from apps.channels.whatsapp_service import WhatsAppService
            service = WhatsAppService.get_for_organization(org)
            if service is None:
                continue
            service.send_message(to=phone, text=message)
        except Exception:
            logger.exception('Daily summary send failed for org %s', org.id)


# ──────────────────────────────────────────────────────────────────────
# Expiry sweep
# ──────────────────────────────────────────────────────────────────────
@shared_task
def check_expiry_task():
    """Create alerts for perishables nearing/past expiry threshold."""
    from .models import InventoryItem, StockMovement, StockAlert

    today = timezone.now().date()
    perishables = InventoryItem.objects.filter(
        is_active=True, is_perishable=True, expiry_days__isnull=False,
    )
    for item in perishables:
        last_in = StockMovement.objects.filter(
            item=item, quantity__gt=0, is_reversed=False,
        ).order_by('-movement_date', '-created_at').first()
        if not last_in:
            continue
        days_since = (today - last_in.movement_date).days
        if days_since < item.expiry_days:
            continue
        already = StockAlert.objects.filter(
            item=item, alert_type=StockAlert.AlertType.EXPIRY, is_resolved=False,
        ).exists()
        if already:
            continue
        StockAlert.objects.create(
            organization=item.organization,
            location=item.location,
            item=item,
            alert_type=StockAlert.AlertType.EXPIRY,
            message=(
                f'{item.name} ({item.sku}) likely past expiry — '
                f'{days_since} day(s) since last received, threshold {item.expiry_days}.'
            ),
        )
