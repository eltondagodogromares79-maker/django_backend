from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0002_chatmessage_reply_reactions'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatroommember',
            name='is_hidden',
            field=models.BooleanField(default=False),
        ),
    ]
