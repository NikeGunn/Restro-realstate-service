# Generated migration for handoff app
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('messaging', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='HandoffAlert',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('alert_type', models.CharField(choices=[('low_confidence', 'Low Confidence'), ('escalation_request', 'Escalation Request'), ('high_intent', 'High Intent Lead'), ('booking_failure', 'Booking Failure'), ('confused_user', 'Confused User'), ('complaint', 'Complaint'), ('other', 'Other')], default='other', max_length=30)),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')], default='medium', max_length=20)),
                ('reason', models.TextField()),
                ('is_acknowledged', models.BooleanField(default=False)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('is_resolved', models.BooleanField(default=False)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolution_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('acknowledged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acknowledged_alerts', to='accounts.user')),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='messaging.conversation')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_alerts', to='accounts.user')),
            ],
            options={
                'db_table': 'handoff_alerts',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EscalationRule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('trigger_type', models.CharField(max_length=50)),
                ('trigger_value', models.JSONField()),
                ('priority', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')], default='high', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('auto_assign_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.user')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='escalation_rules', to='accounts.organization')),
            ],
            options={
                'db_table': 'escalation_rules',
                'ordering': ['name'],
            },
        ),
        migrations.AddIndex(
            model_name='handoffalert',
            index=models.Index(fields=['conversation', '-created_at'], name='handoff_ale_convers_8d5b02_idx'),
        ),
        migrations.AddIndex(
            model_name='handoffalert',
            index=models.Index(fields=['priority', 'is_acknowledged'], name='handoff_ale_priorit_9c2d3e_idx'),
        ),
    ]
