# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-06-01 06:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("import_api", "0002_auto_20180309_1104"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("name", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("displayName", models.CharField(blank=True, max_length=255)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.AlterModelOptions(name="school", options={"ordering": ("name",)}),
    ]
