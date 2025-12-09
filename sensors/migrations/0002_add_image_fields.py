from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sensors', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='profile_picture',
            field=models.ImageField(blank=True, null=True, upload_to='profile_pictures/'),
        ),
        migrations.AddField(
            model_name='maintenance',
            name='picture',
            field=models.ImageField(blank=True, null=True, upload_to='maintenance/'),
        ),
        migrations.AddField(
            model_name='report',
            name='picture',
            field=models.ImageField(blank=True, null=True, upload_to='reports/'),
        ),
        migrations.AlterModelOptions(
            name='maintenance',
            options={'ordering': ['-timestamp']},
        ),
        migrations.AlterModelOptions(
            name='report',
            options={'ordering': ['-timestamp']},
        ),
        migrations.AddField(
            model_name='maintenance',
            name='__str__',
            field=models.CharField(max_length=200, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='report',
            name='__str__',
            field=models.CharField(max_length=200, default=''),
            preserve_default=False,
        ),
    ]
