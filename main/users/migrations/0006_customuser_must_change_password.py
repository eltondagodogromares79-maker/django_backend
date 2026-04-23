from django.db import migrations, models


def set_must_change_password(apps, schema_editor):
    CustomUser = apps.get_model('users', 'CustomUser')
    CustomUser.objects.filter(
        role__in=['student', 'instructor', 'adviser'],
        last_login__isnull=True,
    ).update(must_change_password=True)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_principal_department_alter_adviser_program'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='must_change_password',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(set_must_change_password, migrations.RunPython.noop),
    ]
