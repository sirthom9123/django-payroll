# Generated by Django 4.1 on 2022-08-26 08:10

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Benefits",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Benefits like, i.e. Hospital, Home, Motor",
                        max_length=200,
                    ),
                ),
                (
                    "amount",
                    models.IntegerField(
                        blank=True,
                        default=0,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Deduction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Deductions like, loans, advances", max_length=200
                    ),
                ),
                (
                    "amount",
                    models.IntegerField(
                        blank=True,
                        default=0,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="HR, IT, Operations, etc..", max_length=150, null=True
                    ),
                ),
                ("dedscription", models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="Designation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Junior admin clerk, ect...",
                        max_length=150,
                        null=True,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="designated_department",
                        to="employee.department",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Employee",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("emp_code", models.CharField(blank=True, max_length=10, unique=True)),
                ("first_name", models.CharField(max_length=150, null=True)),
                (
                    "middle_name",
                    models.CharField(blank=True, max_length=150, null=True),
                ),
                ("last_name", models.CharField(max_length=150, null=True)),
                (
                    "maiden_name",
                    models.CharField(blank=True, max_length=150, null=True),
                ),
                ("email_address", models.EmailField(max_length=255, null=True)),
                ("phone", models.CharField(max_length=50, null=True)),
                ("alt_phone", models.CharField(max_length=50, null=True)),
                ("address", models.TextField(blank=True, null=True)),
                ("country", models.CharField(max_length=50, null=True)),
                ("city", models.CharField(max_length=50, null=True)),
                ("postal_code", models.CharField(max_length=20, null=True)),
                ("date_hired", models.DateField(blank=True, null=True)),
                (
                    "date_departed",
                    models.DateField(
                        blank=True,
                        help_text="Employee resigned on this date.",
                        null=True,
                    ),
                ),
                (
                    "employee_type",
                    models.CharField(
                        choices=[
                            ("Full-Time", "Full Time"),
                            ("Part-Time", "Part Time"),
                            ("INTERN", "Intern"),
                            ("Contract", "Contractual"),
                        ],
                        default="Full-Time",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Active", "Active"),
                            ("Suspended", "Suspended"),
                            ("PENDING", "Pending"),
                        ],
                        default="Active",
                        max_length=50,
                        null=True,
                    ),
                ),
                ("created", models.DateField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_owner",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "designation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="designateion",
                        to="employee.designation",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Payroll",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "basic_salary",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        default=0,
                        max_digits=7,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(100)],
                    ),
                ),
                (
                    "rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=7,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "hours",
                    models.DecimalField(
                        blank=True, decimal_places=2, default=0, max_digits=7
                    ),
                ),
                (
                    "income_tax",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        default=0,
                        max_digits=7,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "uif_contribution",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        default=0,
                        max_digits=7,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("start_date", models.DateField(null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("upload_date", models.DateField(blank=True, null=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, null=True)),
                (
                    "benefits",
                    models.ManyToManyField(
                        blank=True,
                        related_name="employee_benefits",
                        to="employee.benefits",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payroll_owner",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deductions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="employee_deductions",
                        to="employee.deduction",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="employee_payroll",
                        to="employee.employee",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BankInfo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("account_number", models.CharField(max_length=150, null=True)),
                ("name", models.CharField(max_length=150, null=True)),
                ("branch_name", models.CharField(max_length=150, null=True)),
                ("branch_code", models.CharField(max_length=10, null=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="employee.employee",
                    ),
                ),
            ],
        ),
    ]