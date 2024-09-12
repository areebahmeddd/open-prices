# Generated by Django 5.1 on 2024-09-12 14:05

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_user_location_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="product_count",
            field=models.PositiveIntegerField(blank=True, default=0, null=True),
        ),
    ]
