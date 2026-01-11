# Generated manually for multilingual support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0002_rename_conversatio_organiz_0a6be4_idx_conversatio_organiz_0461ff_idx_and_more'),
    ]

    operations = [
        # Add detected_language field to Conversation
        migrations.AddField(
            model_name='conversation',
            name='detected_language',
            field=models.CharField(
                choices=[
                    ('en', 'English'),
                    ('zh-CN', '简体中文 (Simplified Chinese)'),
                    ('zh-TW', '繁體中文 (Traditional Chinese)')
                ],
                default='en',
                help_text='Detected language of the customer (auto-updated based on messages)',
                max_length=10,
            ),
        ),
        # Add preferred_language field to WidgetSession
        migrations.AddField(
            model_name='widgetsession',
            name='preferred_language',
            field=models.CharField(
                choices=[
                    ('en', 'English'),
                    ('zh-CN', '简体中文 (Simplified Chinese)'),
                    ('zh-TW', '繁體中文 (Traditional Chinese)')
                ],
                default='en',
                help_text='Preferred language for this session (from browser or user selection)',
                max_length=10,
            ),
        ),
    ]
