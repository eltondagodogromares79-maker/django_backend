from django.db import migrations, models


def set_existing_students_gender(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    CustomUser.objects.filter(role='student', gender='unspecified').update(gender='male')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_passwordresetcode'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='gender',
            field=models.CharField(choices=[('male', 'Male'), ('female', 'Female'), ('unspecified', 'Unspecified')], default='unspecified', max_length=20),
        ),
        migrations.RunPython(set_existing_students_gender, migrations.RunPython.noop),
    ]
