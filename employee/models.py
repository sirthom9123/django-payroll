from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
import textwrap
import uuid
from django.db.models.signals import m2m_changed

from .payroll_math import (
    age_on,
    basic_salary,
    money,
    monthly_paye,
    overtime_pay,
    sum_money,
    uif_on_basic,
)
from .utils import create_ref_code

class HrDocumentStorage(FileSystemStorage):
    def __init__(self, location=None, base_url=None, **kwargs):
        if location is None:
            location = settings.BASE_DIR / "hr_documents"
        if base_url is None:
            base_url = "/hr-documents-not-served/"
        super().__init__(location=location, base_url=base_url, **kwargs)

    def deconstruct(self):
        return ("employee.models.HrDocumentStorage", [], {})


hr_document_storage = HrDocumentStorage()

class EmployeeType(models.TextChoices):
    FULL_TIME = "Full-Time"
    PART_TIME = "Part-Time"
    INTERN = "INTERN"
    CONTRACTUAL = "Contract"
    
    
class Status(models.TextChoices):
    ACTIVE = "Active"
    SUSPENDED = "Suspended"
    PENDING = "PENDING"
    RETIRED = "Retired"


class ContractType(models.TextChoices):
    PERMANENT = "permanent", "Permanent"
    FIXED_TERM = "fixed-term", "Fixed-term"
    INTERN = "intern", "Intern"


class DocumentType(models.TextChoices):
    ID_COPY = "id-copy", "ID copy"
    CONTRACT = "contract", "Contract"
    QUALIFICATION = "qualification", "Qualification"
    OTHER = "other", "Other"
    

class Department(models.Model):
    """Company Departments"""
    name = models.CharField(max_length=150, null=True, help_text='HR, IT, Operations, etc..')
    description = models.TextField(blank=True)
    
    
    def __str__(self):
        return self.name
    
    
class Designation(models.Model):
    """Employee designated working area"""
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='designated_department')
    name = models.CharField(max_length=150, null=True, help_text='Junior admin clerk, ect...')
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name
    

class Employee(models.Model):
    """Employee details"""
    emp_code = models.CharField(max_length=10, blank=True, unique=True) 
    first_name = models.CharField(max_length=150, null=True)
    middle_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, null=True)
    maiden_name = models.CharField(max_length=150, blank=True, null=True)
    id_number = models.CharField(max_length=13, null=True)
    passport = models.CharField(max_length=150, blank=True, null=True)
    email_address = models.EmailField(max_length=255, null=True)
    phone = models.CharField(max_length=50, null=True)
    alt_phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    country = models.CharField(max_length=50, null=True)
    city = models.CharField(max_length=50, null=True) 
    postal_code = models.CharField(max_length=20, null=True)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Used for the PAYE age rebate.",
    )
    
    # Details of employment
    company = models.ForeignKey(
        "company.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT, related_name='designation')
    date_hired = models.DateField(null=True, blank=True, help_text='Employee hired date.')
    days_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        help_text="Days this employee works each week. Family responsibility leave needs at least 4.",
    )
    date_departed = models.DateField(null=True, blank=True, help_text='Employee resigned on this date.')
    gross_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Monthly gross salary or CTC. Payroll uses it until the employee leaves or retires.",
    )
    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Hourly rate for a contract consultant. Payroll uses it until the consultant leaves.",
    )
    pension_number = models.CharField(max_length=13, null=True, blank=True)
    employee_type = models.CharField(
                    max_length=50, choices=EmployeeType.choices, 
                    null=True, default=EmployeeType.FULL_TIME
                )
    status = models.CharField(
                    max_length=50, choices=Status.choices, 
                    null=True, default=Status.ACTIVE
                )
    
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_owner')
    created = models.DateField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    
    def __str__(self):
        return f'Employee: {self.first_name} {self.last_name}'

    def get_full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part)

    def clean(self):
        super().clean()
        if self.date_hired and self.date_departed and self.date_departed < self.date_hired:
            raise ValidationError({
                "date_departed": "Date departed cannot be before date hired.",
            })

    def pay_basis(self):
        """Package pay, or an hourly rate for a contract consultant."""
        current = None
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "contracts" in prefetched:
            for contract in self.contracts.all():
                if contract.is_current:
                    current = contract
                    break
        else:
            current = self.contracts.filter(is_current=True).order_by("-start_date", "-id").first()
        if current and current.contract_type == ContractType.PERMANENT:
            return "package"
        if self.employee_type == EmployeeType.CONTRACTUAL:
            return "hourly"
        return "package"

    def package_applies_on(self, day):
        """The monthly gross stays in use until the employee leaves or retires."""
        if not self.gross_salary:
            return False
        if self.status == Status.RETIRED:
            return False
        if self.date_departed and day and day >= self.date_departed:
            return False
        return True

    def refresh_unpaid_payrolls(self):
        for run in self.employee_payroll.all():
            if not run.has_payment():
                run.save()

    def save(self, *args, **kwargs):
        generate_code = not self.emp_code
        if generate_code:
            self.emp_code = ("T" + uuid.uuid4().hex)[:10]
        previous = None
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk)
                .values_list("gross_salary", "status", "date_departed")
                .first()
            )
        super().save(*args, **kwargs)
        if generate_code:
            name = textwrap.shorten(self.last_name or "", width=3, placeholder="")
            prefix = (name.upper() or "EMP")[:3]
            self.emp_code = f"{prefix}00{self.pk}"[:10]
            super().save(update_fields=["emp_code"])
        current = (self.gross_salary, self.status, self.date_departed)
        if previous is not None and previous != current:
            self.refresh_unpaid_payrolls()
    
    
class Benefits(models.Model):
    name = models.CharField(max_length=200, help_text='Benefits like, i.e. Hospital, Home, Motor')
    amount = models.DecimalField(
                    validators=[MinValueValidator(0),], 
                    null=True, blank=True, default=0,
                    max_digits=7, decimal_places=2
                )


    def __str__(self):
        return str(self.amount)
    
    class Meta:
        verbose_name_plural = 'Benefits'
    

class Deduction(models.Model):
    name = models.CharField(max_length=200, help_text='Deductions like, loans, advances')
    amount = models.DecimalField(
                    validators=[MinValueValidator(0),], 
                    null=True, blank=True, default=0,
                    max_digits=7, decimal_places=2
                )


    def __str__(self):
        return str(self.amount)
    

    
class PaymentMethod(models.TextChoices):
    EFT = "eft", "EFT"
    CASH = "cash", "Cash"


class Payroll(models.Model):
    """Employee salary details"""
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='employee_payroll')
    basic_salary = models.DecimalField(
                        null=True, blank=True,
                        default=0, max_digits=12, decimal_places=2
                    )
    rate = models.DecimalField(
                            null=True, blank=True, max_digits=7, decimal_places=2,
            )
    hours = models.DecimalField(blank=True, max_digits=7, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    overtime_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    income_tax = models.DecimalField(
                    validators=[MinValueValidator(0),],
                    null=True, blank=True, default=0, max_digits=12, decimal_places=2
                )
    uif_contribution = models.DecimalField(
                            null=True, blank=True, default=0, max_digits=12, decimal_places=2
                        )
    benefits = models.ManyToManyField(Benefits, related_name='employee_benefits', blank=True)
    deductions = models.ManyToManyField(Deduction, related_name='employee_deductions', blank=True)
    
    start_date = models.DateField(null=True, help_text='Start Date of payroll')
    end_date = models.DateField(null=True, blank=True,  help_text='Payroll Date') 
    upload_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payroll_owner')
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    
    
    def __str__(self):
        return f'{self.employee.first_name}\'s net salary is {self.get_nett_salary} '

    def has_payment(self):
        if not self.pk:
            return False
        return PayrollPayment.objects.filter(payroll_id=self.pk).exists()

    def clean(self):
        super().clean()
        if self.has_payment():
            raise ValidationError("This payroll run has been paid.")

    def save(self, *args, **kwargs):
        if self.has_payment():
            raise ValidationError("This payroll run has been paid.")
        self.hours = money(self.hours or 0)
        self.overtime_hours = money(self.overtime_hours or 0)
        self.overtime_rate = money(self.overtime_rate or 0)
        if self.rate in (None, "") or Decimal(self.rate) == 0:
            self.rate = None
            self.basic_salary = self._package_basic()
        else:
            self.rate = money(self.rate)
            self.basic_salary = basic_salary(self.rate, self.hours)
        self.uif_contribution = uif_on_basic(self.basic_salary)
        self.income_tax = self._calculated_paye()
        if self.upload_date is None:
            self.upload_date = timezone.now()
        return super().save(*args, **kwargs)

    def _package_basic(self):
        if self.employee_id and self.employee.package_applies_on(self.start_date):
            return money(self.employee.gross_salary)
        return money(0)

    def _calculated_paye(self):
        if not self.start_date or not self.employee_id:
            return money(self.income_tax or 0)
        year = TaxYear.for_date(self.start_date)
        if year is None:
            return money(self.income_tax or 0)
        rebate, _note = year.rebate_for(self.employee.date_of_birth)
        try:
            return monthly_paye(self._remuneration_for_paye(), list(year.bands.all()), rebate)
        except ValueError:
            raise ValidationError("The PAYE table for this date has no band for this remuneration.")

    def _remuneration_for_paye(self):
        if not self.pk:
            return money(Decimal(self.basic_salary or 0) + self.overtime_amount)
        return self.get_gross_salary

    def paye_explanation(self):
        if not self.start_date:
            return None
        year = TaxYear.for_date(self.start_date)
        if year is None:
            return None
        remuneration = self.get_gross_salary
        rebate, note = year.rebate_for(self.employee.date_of_birth if self.employee_id else None)
        return {
            "year_name": year.name,
            "remuneration": remuneration,
            "annual": remuneration * 12,
            "rebate": rebate,
            "note": note,
        }

    @property
    def overtime_amount(self):
        return overtime_pay(self.overtime_hours, self.overtime_rate)

    @property
    def allowance_total(self):
        return sum_money(line.amount for line in self.allowance_lines.all())

    @property
    def deduction_line_total(self):
        return sum_money(line.amount for line in self.deduction_lines.all())
    
    @property
    def get_gross_salary(self):
        return money(
            Decimal(self.basic_salary or 0)
            + self.overtime_amount
            + self.get_selected_benefits
            + self.allowance_total
        )
    
    @property
    def get_nett_salary(self):
        return money(self.get_gross_salary - self.get_total_deductions)

    @property
    def get_selected_benefits(self):
        return sum_money(item.amount for item in self.benefits.all())

    @property
    def get_selected_deductions(self):
        return sum_money(item.amount for item in self.deductions.all())
    
    @property
    def get_total_deductions(self):
        return money(
            Decimal(self.income_tax or 0)
            + Decimal(self.uif_contribution or 0)
            + self.get_selected_deductions
            + self.deduction_line_total
        )


class AllowanceLine(models.Model):
    """An allowance that belongs to one payroll run, not the shared catalogue."""
    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name="allowance_lines")
    name = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), message="Enter an amount greater than zero.")],
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} {self.amount}"

    def clean(self):
        super().clean()
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")

    def save(self, *args, **kwargs):
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")
        self.amount = money(self.amount)
        super().save(*args, **kwargs)
        self._refresh_payroll_paye()

    def delete(self, *args, **kwargs):
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")
        payroll = self.payroll
        result = super().delete(*args, **kwargs)
        if payroll.pk and not payroll.has_payment():
            payroll.save()
        return result

    def _refresh_payroll_paye(self):
        if self.payroll_id and not self.payroll.has_payment():
            self.payroll.save()


class DeductionLine(models.Model):
    """A deduction that belongs to one payroll run, not the shared catalogue."""
    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name="deduction_lines")
    name = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), message="Enter an amount greater than zero.")],
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} {self.amount}"

    def clean(self):
        super().clean()
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")

    def save(self, *args, **kwargs):
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")
        self.amount = money(self.amount)
        super().save(*args, **kwargs)
        if self.payroll_id and not self.payroll.has_payment():
            self.payroll.save()

    def delete(self, *args, **kwargs):
        if self.payroll_id and self.payroll.has_payment():
            raise ValidationError("This payroll run has been paid.")
        payroll = self.payroll
        result = super().delete(*args, **kwargs)
        if payroll.pk and not payroll.has_payment():
            payroll.save()
        return result


class PayrollPayment(models.Model):
    payroll = models.OneToOneField(Payroll, on_delete=models.PROTECT, related_name="payment")
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    payment_date = models.DateField()
    reference = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_payments")
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_method_display()} {self.amount}"


class TaxYear(models.Model):
    """One South African tax year of PAYE bands and rebates."""
    name = models.CharField(max_length=20, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    primary_rebate = models.DecimalField(max_digits=12, decimal_places=2)
    secondary_rebate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Added when the employee is 65 or older on the last day of this tax year.",
    )
    tertiary_rebate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Added, with the secondary rebate, when the employee is 75 or older on that day.",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})
        if self.start_date and self.end_date:
            overlap = TaxYear.objects.filter(
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            other = overlap.first()
            if other:
                raise ValidationError(f"This tax year overlaps {other.name}.")

    @classmethod
    def for_date(cls, day):
        if day is None:
            return None
        return cls.objects.filter(start_date__lte=day, end_date__gte=day).first()

    def rebate_for(self, date_of_birth):
        rebate = Decimal(self.primary_rebate or 0)
        if not date_of_birth:
            return rebate, "Primary rebate only. Add a date of birth to apply an age rebate."
        age = age_on(date_of_birth, self.end_date)
        if age >= 65:
            rebate += Decimal(self.secondary_rebate or 0)
        if age >= 75:
            rebate += Decimal(self.tertiary_rebate or 0)
        if age >= 75:
            note = "Primary, secondary, and tertiary rebates applied."
        elif age >= 65:
            note = "Primary and secondary rebates applied."
        else:
            note = "Primary rebate applied."
        return rebate, note

    def refresh_unpaid_runs(self):
        runs = Payroll.objects.filter(
            start_date__gte=self.start_date,
            start_date__lte=self.end_date,
        ).select_related("employee")
        updated = 0
        paid = 0
        for run in runs:
            if run.has_payment():
                paid += 1
                continue
            run.save()
            updated += 1
        return updated, paid


class TaxBand(models.Model):
    tax_year = models.ForeignKey(TaxYear, on_delete=models.CASCADE, related_name="bands")
    income_from = models.DecimalField(max_digits=12, decimal_places=2)
    income_to = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))],
    )
    base_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    above_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["income_from", "id"]

    def __str__(self):
        ceiling = self.income_to if self.income_to is not None else "and above"
        return f"{self.tax_year} {self.income_from}–{ceiling} at {self.rate_percent}%"


def _refresh_paye_from_benefits(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"} and not instance.has_payment():
        instance.save()


m2m_changed.connect(
    _refresh_paye_from_benefits,
    sender=Payroll.benefits.through,
    dispatch_uid="employee.payroll.benefits.paye",
)


class BankInfo(models.Model):
    account_number = models.CharField(max_length=150, null=True)
    name = models.CharField(max_length=150, null=True, help_text='Bank Name')
    branch_name = models.CharField(max_length=150, null=True)
    branch_code = models.CharField(max_length=10, null=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    
    def __str__(self):
        return f'{self.employee} banks at {self.name}'

    def masked_account_number(self):
        raw = self.account_number or ""
        digits = "".join(character for character in raw if character.isdigit())
        if len(digits) < 4:
            return ""
        return f"•••• {digits[-4:]}"


class Contract(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField(max_length=20, choices=ContractType.choices)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    job_title = models.CharField(max_length=150)
    job_description = models.TextField(blank=True)
    notice_period_days = models.PositiveIntegerField(help_text="Notice period in days")
    signed_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_current", "-start_date", "-id"]

    def __str__(self):
        return f"{self.employee} — {self.job_title}"

    def clean(self):
        super().clean()
        if self.contract_type == ContractType.FIXED_TERM and not self.end_date:
            raise ValidationError({
                "end_date": "End date is required for a fixed-term contract.",
            })
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                "end_date": "End date must be on or after the start date.",
            })

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            Contract.objects.filter(employee=self.employee, is_current=True).exclude(pk=self.pk).update(is_current=False)


class Qualification(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="qualifications")
    institution = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    year_completed = models.PositiveIntegerField(
        validators=[MinValueValidator(1950), MaxValueValidator(2100)],
    )
    nqf_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )

    class Meta:
        ordering = ["-year_completed", "name"]

    def __str__(self):
        return f"{self.name} ({self.institution})"


class EmploymentHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employment_history")
    employer = models.CharField(max_length=200)
    role = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reason_for_leaving = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        verbose_name_plural = "Employment history"

    def __str__(self):
        return f"{self.role} at {self.employer}"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                "end_date": "End date cannot be before the start date.",
            })


def hr_document_path(instance, filename):
    return f"{instance.employee_id}/{filename}"


class EmployeeDocument(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(upload_to=hr_document_path, storage=hr_document_storage)
    date_added = models.DateField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_documents")

    class Meta:
        ordering = ["-date_added", "-id"]

    def __str__(self):
        return self.title
    



    
    
    