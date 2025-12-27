# Generated migration for ai_engine app
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
            name='AILog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('prompt', models.TextField()),
                ('response', models.TextField()),
                ('model', models.CharField(default='gpt-4o-mini', max_length=50)),
                ('tokens_used', models.IntegerField(default=0)),
                ('confidence_score', models.FloatField(blank=True, null=True)),
                ('processing_time', models.FloatField(blank=True, null=True)),
                ('error', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_logs', to='messaging.conversation')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_logs', to='accounts.organization')),
            ],
            options={
                'verbose_name': 'AI log',
                'verbose_name_plural': 'AI logs',
                'db_table': 'ai_logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
