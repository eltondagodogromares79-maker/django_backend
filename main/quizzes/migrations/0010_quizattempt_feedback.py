from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0009_quiz_is_available'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizattempt',
            name='feedback',
            field=models.TextField(blank=True, null=True),
        ),
    ]
