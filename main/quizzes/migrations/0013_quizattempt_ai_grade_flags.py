from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0012_quizfilterpreference_score_feedback_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizattempt',
            name='ai_grade_applied',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='quizattempt',
            name='ai_grade_failed',
            field=models.BooleanField(default=False),
        ),
    ]

