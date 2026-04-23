from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0003_chatroommember_is_hidden'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatroommember',
            name='cleared_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
