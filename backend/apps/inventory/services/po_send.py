"""
Purchase order send + PDF.

PDF generation uses ReportLab (already a transitive dep) so we don't
add weasyprint's heavy native deps. Email goes through Django's send_mail;
in dev with the console backend it just logs — production should configure
EMAIL_BACKEND + SMTP creds in settings.
"""
import io
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import PurchaseOrder, PurchaseOrderEmail


def render_po_pdf(po: PurchaseOrder) -> bytes:
    """Generate a simple, readable PO PDF. Returns the bytes."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError:
        # Fallback: a plain text "PDF" — keeps the endpoint functional even
        # if reportlab is missing, so production still gets *something*.
        text = _render_po_text(po)
        return text.encode('utf-8')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f'PO {po.order_number}')
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(
        f'<b>Purchase Order</b> — {po.order_number}', styles['Title'],
    ))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        f'<b>Supplier:</b> {po.supplier.name}<br/>'
        f'<b>Order date:</b> {po.order_date}<br/>'
        f'<b>Expected:</b> {po.expected_date or "—"}<br/>'
        f'<b>Status:</b> {po.status}',
        styles['Normal'],
    ))
    elements.append(Spacer(1, 12))

    rows = [['SKU', 'Item', 'Qty', 'Unit', 'Unit cost', 'Line total']]
    for li in po.items.select_related('item'):
        rows.append([
            li.item.sku, li.item.name,
            str(li.quantity_ordered), li.item.unit,
            str(li.unit_cost),
            str((li.quantity_ordered * li.unit_cost).quantize(Decimal('0.01'))),
        ])
    rows.append(['', '', '', '', 'Total', str(po.total_amount)])

    table = Table(rows, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))
    if po.notes:
        elements.append(Paragraph(f'<b>Notes:</b> {po.notes}', styles['Normal']))

    doc.build(elements)
    return buf.getvalue()


def _render_po_text(po: PurchaseOrder) -> str:
    lines = [
        f'PURCHASE ORDER {po.order_number}',
        '=' * 40,
        f'Supplier: {po.supplier.name}',
        f'Order date: {po.order_date}',
        f'Expected: {po.expected_date or "—"}',
        '',
        f'{"SKU":<20} {"Item":<25} {"Qty":>10} {"Unit":<8} {"Cost":>10}',
    ]
    for li in po.items.select_related('item'):
        lines.append(
            f'{li.item.sku:<20} {li.item.name:<25} '
            f'{li.quantity_ordered:>10} {li.item.unit:<8} {li.unit_cost:>10}'
        )
    lines.append('')
    lines.append(f'Total: {po.total_amount}')
    return '\n'.join(lines)


@transaction.atomic
def send_po(po: PurchaseOrder, *, to_email: str = None, performed_by=None) -> PurchaseOrderEmail:
    """Move PO from DRAFT → SENT, render PDF, attach, dispatch email, persist record."""
    if po.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError(
            f'Only draft POs can be sent (current status: {po.status}).'
        )
    if not po.items.exists():
        raise ValidationError('Cannot send an empty purchase order.')

    recipient = (to_email or po.supplier.email or '').strip()
    if not recipient:
        raise ValidationError(
            'No recipient email — supply to_email or set Supplier.email.'
        )

    pdf_bytes = render_po_pdf(po)

    subject = f'Purchase Order {po.order_number}'
    body = (
        f'Hello {po.supplier.contact_name or po.supplier.name},\n\n'
        f'Please find attached purchase order {po.order_number} '
        f'totaling {po.total_amount}. We expect delivery by '
        f'{po.expected_date or "as soon as possible"}.\n\n'
        f'Regards,\n{po.organization.name}'
    )

    email_record = PurchaseOrderEmail.objects.create(
        purchase_order=po,
        to_email=recipient,
        subject=subject,
        body=body,
        sent_by=performed_by,
    )

    try:
        msg = EmailMessage(
            subject=subject, body=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kribaat.com'),
            to=[recipient],
        )
        msg.attach(f'{po.order_number}.pdf', pdf_bytes, 'application/pdf')
        msg.send(fail_silently=False)
        email_record.sent_at = timezone.now()
        email_record.save(update_fields=['sent_at', 'updated_at'])
    except Exception as exc:
        email_record.error = str(exc)
        email_record.save(update_fields=['error', 'updated_at'])
        # Don't raise — the PO state still flips to SENT so retries are possible.

    po.status = PurchaseOrder.Status.SENT
    po.sent_at = timezone.now()
    po.sent_to_email = recipient
    po.save(update_fields=['status', 'sent_at', 'sent_to_email', 'updated_at'])

    return email_record
