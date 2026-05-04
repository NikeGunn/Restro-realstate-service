from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_location_options_alter_organization_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='plan_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
