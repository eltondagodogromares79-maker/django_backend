from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('learning_materials', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='learningmaterial',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='learning_materials/'),
        ),
        migrations.AlterField(
            model_name='learningmaterial',
            name='type',
            field=models.CharField(choices=[('pdf', 'PDF'), ('image', 'Image'), ('text', 'Text'), ('link', 'Link'), ('video', 'Video')], max_length=10),
        ),
    ]
