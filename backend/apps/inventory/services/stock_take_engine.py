"""
StockTakeEngine — physical count → variance → adjustment movements.

A committed StockTake emits one ADJUSTMENT StockMovement per line whose
counted differs from system_count, routed through StockEngine so the
ledger remains the single source of truth.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import StockMovement, StockTake


class StockTakeEngine:
    @staticmethod
    @transaction.atomic
    def commit(stock_take: StockTake, performed_by=None) -> dict:
        if stock_take.status != StockTake.Status.IN_PROGRESS:
            raise ValidationError(
                f'StockTake is in status {stock_take.status}; cannot commit.'
            )
        from .stock_engine import StockEngine
        engine = StockEngine(
            organization=stock_take.organization,
            location=stock_take.location,
            performed_by=performed_by,
        )

        adjustments = 0
        no_change = 0
        for line in stock_take.lines.select_related('item'):
            variance = line.counted - line.system_count
            if variance == 0:
                no_change += 1
                continue
            engine._create_movement(
                item=line.item,
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                quantity=variance,
                notes=(
                    f'Stock-take {stock_take.id}: counted={line.counted} '
                    f'system={line.system_count} variance={variance}'
                ),
                reference_id=str(stock_take.id),
                reference_type='stock_take',
            )
            adjustments += 1

        stock_take.status = StockTake.Status.COMMITTED
        stock_take.committed_at = timezone.now()
        stock_take.save(update_fields=['status', 'committed_at', 'updated_at'])

        return {
            'stock_take_id': str(stock_take.id),
            'adjustments_created': adjustments,
            'no_change_lines': no_change,
        }
