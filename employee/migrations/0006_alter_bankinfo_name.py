# Generated by Django 4.1 on 2022-08-26 14:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0005_alter_benefits_amount_alter_deduction_amount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bankinfo",
            name="name",
            field=models.CharField(help_text="Bank Name", max_length=150, null=True),
        ),
    ]
