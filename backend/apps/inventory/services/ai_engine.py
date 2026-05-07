"""
InventoryAIEngine — Plane B
===========================
Admin-only AI assistant for inventory questions. Completely separate from
apps.ai_engine.services.AIService. Shares only the OPENAI_API_KEY setting.

- Grounded only: answers based on real DB data injected into the prompt.
- Confidence < 0.70 → answer is replaced with a safe deflection.
- Every query is recorded in InventoryAuditLog as action='ai_query'.
- Prompts live in apps/inventory/prompts/*.txt — never inline strings.
"""
import json
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings


PROMPT_DIR = Path(__file__).resolve().parent.parent / 'prompts'
logger = logging.getLogger(__name__)


class InventoryAIEngine:
    CONFIDENCE_THRESHOLD = 0.70

    def __init__(self, model: str = None):
        self.model = (
            model
            or getattr(settings, 'INVENTORY_SETTINGS', {}).get('AI_INVENTORY_MODEL')
            or getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        )

    # ──────────────────────────────────────────────────────────────
    # Prompt assembly
    # ──────────────────────────────────────────────────────────────
    def _load_prompt(self, filename: str) -> str:
        return (PROMPT_DIR / filename).read_text(encoding='utf-8')

    def _build_stock_context(self, organization, location=None) -> str:
        from apps.inventory.models import InventoryItem, StockMovement, StockAlert
        from .tolerance_engine import ToleranceEngine

        items_qs = InventoryItem.objects.filter(
            organization=organization, is_active=True,
        ).select_related('category', 'supplier')
        if location:
            items_qs = items_qs.filter(location=location)
        items = list(items_qs[:50])

        lines = ['=== CURRENT STOCK ===']
        for item in items:
            es = ToleranceEngine.effective_stock(
                item.current_stock, item.reorder_level, item.tolerance_percent,
            )
            if es.is_negative:
                status = 'NEGATIVE'
            elif es.is_critical:
                status = 'CRITICAL'
            elif item.reorder_level > 0 and es.raw <= item.reorder_level * 2:
                status = 'LOW'
            else:
                status = 'OK'
            lines.append(
                f'{item.sku} | {item.name} | {es.reported} {item.unit} '
                f'| {status} | reorder@{item.reorder_level}'
            )

        alerts = list(
            StockAlert.objects.filter(
                organization=organization, is_resolved=False,
            ).select_related('item')[:10]
        )
        if alerts:
            lines.append('\n=== ACTIVE ALERTS ===')
            for a in alerts:
                lines.append(f'{a.alert_type} :: {a.item.name} :: {a.message}')

        recent = list(
            StockMovement.objects.filter(
                organization=organization, is_reversed=False,
            ).select_related('item').order_by('-movement_date', '-created_at')[:20]
        )
        if recent:
            lines.append('\n=== RECENT MOVEMENTS (last 20) ===')
            for m in recent:
                sign = '+' if m.quantity > 0 else ''
                lines.append(
                    f'{m.movement_date} | {m.item.name} | {sign}{m.quantity} '
                    f'{m.item.unit} | {m.movement_type}'
                )
        return '\n'.join(lines)

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────
    def query(self, question: str, organization, location=None, user=None) -> dict:
        from apps.inventory.models import InventoryAuditLog, InventoryItem

        question = (question or '').strip()
        if not question:
            return {
                'answer': 'Please ask a question about your inventory.',
                'confidence': 0.0,
                'data_points_used': [],
            }

        # Cheap pre-flight: if there's no inventory at all, skip OpenAI and say so.
        item_count = InventoryItem.objects.filter(
            organization=organization, is_active=True,
        ).count()
        if item_count == 0:
            return {
                'answer': (
                    'Your inventory is empty. Add items, suppliers, and movements first '
                    'so the AI has real data to ground its answers in.'
                ),
                'confidence': 0.0,
                'data_points_used': [],
            }

        context = self._build_stock_context(organization, location)
        template = self._load_prompt('inventory_query.txt')
        prompt = template.format(
            organization_name=organization.name,
            stock_context=context,
            question=question,
        )

        result = self._call_openai(prompt)
        confidence = float(result.get('confidence', 0.0))
        if confidence < self.CONFIDENCE_THRESHOLD:
            result['answer'] = (
                "I don't have enough data to answer that accurately. "
                'Please check the inventory dashboard directly.'
            )
            result['confidence'] = confidence

        # Audit log — AI queries are visible in the audit trail.
        try:
            InventoryAuditLog.objects.create(
                organization=organization,
                location=location,
                action='ai_query',
                model_name='InventoryAIEngine',
                object_id=organization.id,
                object_repr=f'Q: {question[:180]}',
                after={
                    'question': question,
                    'answer': result.get('answer'),
                    'confidence': confidence,
                    'data_points_used': result.get('data_points_used', []),
                    'model': self.model,
                },
                performed_by=user,
            )
        except Exception:
            logger.exception('Failed to write inventory AI audit log')

        return result

    def generate_stock_alert_message(self, item) -> str:
        from .tolerance_engine import ToleranceEngine
        es = ToleranceEngine.effective_stock(
            item.current_stock, item.reorder_level, item.tolerance_percent,
        )
        return self._load_prompt('stock_alert.txt').format(
            item_name=item.name,
            current_stock=es.reported,
            unit=item.unit,
            reorder_level=item.reorder_level,
            sku=item.sku,
        )

    def generate_daily_summary(self, organization, summary_lines: list) -> str:
        return self._load_prompt('daily_summary.txt').format(
            organization_name=organization.name,
            summary_lines='\n'.join(summary_lines) if summary_lines else 'No notable activity.',
        )

    def insights(self, organization) -> dict:
        """
        Weekly Plane B insights: pulls reorder forecast, waste, and recent
        movements, asks the model for a tight paragraph. Falls back to a
        deterministic digest when OPENAI_API_KEY is not configured.
        """
        from .analytics import reorder_forecast, waste_analysis
        org_ids = [organization.id]
        forecast = reorder_forecast(org_ids, days=7)[:5]
        waste = waste_analysis(org_ids, days=7)

        digest_lines = ['Reorder candidates (top 5):']
        if forecast:
            for r in forecast:
                digest_lines.append(
                    f"  - {r['item_name']} stock={r['current_stock']} "
                    f"avg/day={r['avg_daily_consumption']} cover={r['days_of_cover']}d"
                )
        else:
            digest_lines.append('  (none)')
        digest_lines.append('Top wasted items this week:')
        if waste['top_items']:
            for w in waste['top_items'][:5]:
                digest_lines.append(
                    f"  - {w['item_name']}: {w['wasted']} {w['unit']} "
                    f"({w['event_count']} events)"
                )
        else:
            digest_lines.append('  (none)')

        digest = '\n'.join(digest_lines)

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            return {
                'answer': digest,
                'confidence': 1.0,
                'data_points_used': ['reorder_forecast', 'waste_analysis'],
            }
        prompt = self._load_prompt('weekly_insights.txt').format(
            organization_name=organization.name,
            digest=digest,
        )
        return self._call_openai(prompt)

    # ──────────────────────────────────────────────────────────────
    # OpenAI call (defensive — degrades gracefully without API key)
    # ──────────────────────────────────────────────────────────────
    def _call_openai(self, prompt: str) -> dict:
        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            return {
                'answer': 'AI service is not configured for this environment.',
                'confidence': 0.0,
                'data_points_used': [],
            }
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                response_format={'type': 'json_object'},
                temperature=0.1,
                max_tokens=600,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            return {
                'answer': data.get('answer', ''),
                'confidence': float(data.get('confidence', 0.0)),
                'data_points_used': data.get('data_points_used', []),
            }
        except Exception as e:
            logger.warning('InventoryAIEngine OpenAI call failed: %s', e)
            return {
                'answer': 'AI service is temporarily unavailable. Please try again later.',
                'confidence': 0.0,
                'data_points_used': [],
            }
