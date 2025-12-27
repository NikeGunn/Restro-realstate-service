# Generated migration for messaging app
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('channel', models.CharField(choices=[('website', 'Website Widget'), ('whatsapp', 'WhatsApp'), ('instagram', 'Instagram')], default='website', max_length=20)),
                ('channel_conversation_id', models.CharField(blank=True, max_length=255, help_text='External conversation ID from the channel (e.g., WhatsApp thread ID)')),
                ('state', models.CharField(choices=[('new', 'New'), ('ai_handling', 'AI Handling'), ('awaiting_user', 'Awaiting User'), ('human_handoff', 'Human Handoff'), ('resolved', 'Resolved'), ('archived', 'Archived')], default='new', max_length=20)),
                ('customer_name', models.CharField(blank=True, max_length=255)),
                ('customer_email', models.EmailField(blank=True, max_length=254)),
                ('customer_phone', models.CharField(blank=True, max_length=20)),
                ('customer_metadata', models.JSONField(blank=True, default=dict)),
                ('intent', models.CharField(blank=True, max_length=100)),
                ('sentiment', models.CharField(blank=True, max_length=50)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('is_locked', models.BooleanField(default=False)),
                ('locked_at', models.DateTimeField(blank=True, null=True)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_conversations', to='accounts.user')),
                ('locked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='locked_conversations', to='accounts.user')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='conversations', to='accounts.location')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='accounts.organization')),
            ],
            options={
                'db_table': 'conversations',
                'ordering': ['-last_message_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('sender', models.CharField(choices=[('customer', 'Customer'), ('ai', 'AI Assistant'), ('human', 'Human Agent'), ('system', 'System')], default='customer', max_length=20)),
                ('channel_message_id', models.CharField(blank=True, max_length=255, help_text='External message ID from the channel')),
                ('confidence_score', models.FloatField(blank=True, null=True)),
                ('intent', models.CharField(blank=True, max_length=100)),
                ('ai_metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_read', models.BooleanField(default=False)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='messaging.conversation')),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_messages', to='accounts.user')),
            ],
            options={
                'db_table': 'messages',
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='WidgetSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('session_token', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('visitor_id', models.CharField(blank=True, max_length=255)),
                ('user_agent', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('referrer', models.URLField(blank=True)),
                ('page_url', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_activity_at', models.DateTimeField(auto_now=True)),
                ('conversation', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='widget_session', to='messaging.conversation')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.location')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='widget_sessions', to='accounts.organization')),
            ],
            options={
                'db_table': 'widget_sessions',
                'ordering': ['-last_activity_at'],
            },
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['organization', 'state'], name='conversatio_organiz_0a6be4_idx'),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['channel', 'channel_conversation_id'], name='conversatio_channel_8e4a5e_idx'),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['-last_message_at'], name='conversatio_last_ms_9f2c1a_idx'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['conversation', 'created_at'], name='messages_convers_e95a22_idx'),
        ),
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['channel_message_id'], name='messages_channel_f8d3a1_idx'),
        ),
    ]

