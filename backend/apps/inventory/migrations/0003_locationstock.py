"""
Phase 4 — multi-location stock split.

Adds LocationStock(item, location, current_stock, reorder_level_override)
as the per-location projection of the StockMovement ledger, then backfills
one row per existing (item, location) group from the historical ledger.

Backfill is idempotent (update_or_create) and verifies that
sum(LocationStock.current_stock per item) == InventoryItem.current_stock,
logging any drift but never aborting — production data must migrate.
"""
import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def backfill_location_stock(apps, schema_editor):
    InventoryItem = apps.get_model('inventory', 'InventoryItem')
    StockMovement = apps.get_model('inventory', 'StockMovement')
    LocationStock = apps.get_model('inventory', 'LocationStock')

    from django.db.models import Sum

    # Group every non-reversed movement by (item_id, location_id), sum quantities,
    # and project into LocationStock. Handles location=NULL as its own bucket.
    grouped = (
        StockMovement.objects
        .filter(is_reversed=False)
        .values('item_id', 'location_id')
        .annotate(total=Sum('quantity'))
    )

    created = 0
    updated = 0
    for row in grouped:
        item_id = row['item_id']
        location_id = row['location_id']
        total = row['total'] or Decimal('0')
        obj, was_created = LocationStock.objects.update_or_create(
            item_id=item_id,
            location_id=location_id,
            defaults={'current_stock': total},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    # Sanity check: per-item sum should match item.current_stock.
    drift = []
    for item in InventoryItem.objects.all():
        ls_total = (
            LocationStock.objects.filter(item=item)
            .aggregate(s=Sum('current_stock'))['s']
            or Decimal('0')
        )
        if ls_total != item.current_stock:
            drift.append((str(item.pk), str(item.current_stock), str(ls_total)))

    if drift:
        import logging
        logging.getLogger('inventory.migrations').warning(
            'LocationStock backfill drift detected for %d item(s): %s',
            len(drift), drift[:20],
        )


def noop_reverse(apps, schema_editor):
    # Reverse migration drops the table via the schema op; no data action needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_purchaseorder_recipe_supplierimport_salesimport_and_more'),
        ('accounts', '0003_organization_plan_expires_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='LocationStock',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, editable=False, primary_key=True, serialize=False,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('current_stock', models.DecimalField(
                    decimal_places=4, default=Decimal('0'), max_digits=12,
                    help_text='Per-location stock projection. Maintained by the StockMovement signal.',
                )),
                ('reorder_level_override', models.DecimalField(
                    decimal_places=4, max_digits=10, null=True, blank=True,
                    help_text='Optional per-location reorder level. Falls back to item.reorder_level when null.',
                )),
                ('item', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='location_stocks',
                    to='inventory.inventoryitem',
                )),
                ('location', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='item_stocks',
                    to='accounts.location',
                )),
            ],
            options={
                'verbose_name': 'Location Stock',
                'verbose_name_plural': 'Location Stocks',
                'db_table': 'inv_location_stock',
            },
        ),
        migrations.AddConstraint(
            model_name='locationstock',
            constraint=models.UniqueConstraint(
                condition=models.Q(('location__isnull', False)),
                fields=('item', 'location'),
                name='uniq_location_stock_item_location',
            ),
        ),
        migrations.AddConstraint(
            model_name='locationstock',
            constraint=models.UniqueConstraint(
                condition=models.Q(('location__isnull', True)),
                fields=('item',),
                name='uniq_location_stock_item_null_location',
            ),
        ),
        migrations.AddIndex(
            model_name='locationstock',
            index=models.Index(fields=['item', 'location'], name='inv_locatio_item_id_loc_idx'),
        ),
        migrations.RunPython(backfill_location_stock, noop_reverse),
    ]
