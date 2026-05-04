import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0003_organization_plan_expires_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.CharField(db_index=True, help_text='Case-insensitive; stored uppercased. Shown to users as-is.', max_length=64, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('plan_granted', models.CharField(choices=[('basic', 'Basic'), ('power', 'Power')], default='power', help_text='Plan tier granted on redemption.', max_length=20)),
                ('duration_days', models.PositiveIntegerField(default=30, help_text='How many days the granted plan stays active after redemption.')),
                ('max_redemptions', models.PositiveIntegerField(blank=True, help_text='Total redemption cap across all orgs. Blank = unlimited.', null=True)),
                ('redemption_count', models.PositiveIntegerField(default=0, editable=False)),
                ('valid_from', models.DateTimeField(blank=True, null=True)),
                ('valid_until', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coupons_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'coupons',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CouponRedemption',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('redeemed_at', models.DateTimeField(auto_now_add=True)),
                ('granted_until', models.DateTimeField()),
                ('coupon', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='redemptions', to='coupons.coupon')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coupon_redemptions', to='accounts.organization')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coupon_redemptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'coupon_redemptions',
                'ordering': ['-redeemed_at'],
                'unique_together': {('coupon', 'organization')},
            },
        ),
    ]
