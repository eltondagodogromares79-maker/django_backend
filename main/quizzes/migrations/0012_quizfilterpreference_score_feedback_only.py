from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0011_quizanswer_feedback_quizfilterpreference'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizfilterpreference',
            name='score_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='quizfilterpreference',
            name='feedback_only',
            field=models.BooleanField(default=False),
        ),
    ]
