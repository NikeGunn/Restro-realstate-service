# Generated migration for knowledge app
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
            name='KnowledgeBase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('business_description', models.TextField(blank=True, help_text='Description of the business for AI context')),
                ('opening_hours', models.JSONField(blank=True, default=dict, help_text='Opening hours for each day of the week')),
                ('contact_info', models.JSONField(blank=True, default=dict, help_text='Contact details (phone, email, address, etc.)')),
                ('services', models.JSONField(blank=True, default=list, help_text='List of services offered')),
                ('additional_info', models.TextField(blank=True, help_text='Any additional information for AI context')),
                ('policies', models.JSONField(blank=True, default=dict, help_text='Business policies (cancellation, refund, etc.)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('location', models.ForeignKey(blank=True, help_text='If set, this knowledge overrides org-level for this location', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_bases', to='accounts.location')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledge_bases', to='accounts.organization')),
            ],
            options={
                'db_table': 'knowledge_bases',
                'ordering': ['organization', 'location'],
            },
        ),
        migrations.AddConstraint(
            model_name='knowledgebase',
            constraint=models.UniqueConstraint(fields=['organization', 'location'], name='unique_org_location'),
        ),
        migrations.CreateModel(
            name='FAQ',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('question', models.TextField()),
                ('answer', models.TextField()),
                ('order', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('knowledge_base', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='faqs', to='knowledge.knowledgebase')),
            ],
            options={
                'verbose_name': 'FAQ',
                'verbose_name_plural': 'FAQs',
                'db_table': 'faqs',
                'ordering': ['order', '-created_at'],
            },
        ),
    ]
