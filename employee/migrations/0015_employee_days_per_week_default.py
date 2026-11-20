from django.db import migrations, models
import django.core.validators


def set_days_per_week_where_blank(apps, schema_editor):
    Employee = apps.get_model("employee", "Employee")
    Employee.objects.filter(days_per_week__isnull=True).update(days_per_week=5)


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0014_statutory_parental_holiday_accrual"),
    ]

    operations = [
        migrations.RunPython(set_days_per_week_where_blank, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="employee",
            name="days_per_week",
            field=models.PositiveSmallIntegerField(
                blank=True,
                default=5,
                help_text="Days this employee works each week. Family responsibility leave needs at least 4.",
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(7)],
            ),
        ),
    ]