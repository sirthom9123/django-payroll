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
    date_departed = models.DateField(null=True, blank=True, help_text='Employee resigned on this date.')
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

    def save(self, *args, **kwargs):
        generate_code = not self.emp_code
        if generate_code:
            self.emp_code = ("T" + uuid.uuid4().hex)[:10]
        super().save(*args, **kwargs)
        if generate_code:
            name = textwrap.shorten(self.last_name or "", width=3, placeholder="")
            prefix = (name.upper() or "EMP")[:3]
            self.emp_code = f"{prefix}00{self.pk}"[:10]
            super().save(update_fields=["emp_code"])
    
    
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
    

    
class Payroll(models.Model):
    """Employee salary details"""
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='employee_payroll')
    basic_salary = models.DecimalField( 
                        null=True, blank=True,
                        default=0, max_digits=7, decimal_places=2
                    )
    rate = models.DecimalField(
                            blank=True, max_digits=7, decimal_places=2, 
                            validators=[MinValueValidator(1),]
            )
    hours = models.DecimalField(blank=True, max_digits=7, decimal_places=2, default=0)
    
    income_tax = models.DecimalField(
                    validators=[MinValueValidator(0),], 
                    null=True, blank=True, default=0, max_digits=7, decimal_places=2
                )
    uif_contribution = models.DecimalField(
                            null=True, blank=True, default=0, max_digits=7, decimal_places=2
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
    
    
    def save(self, *args, **kwargs):
        self.basic_salary = self.rate * self.hours
        self.uif_contribution = self.basic_salary * Decimal(0.01)
        if self.upload_date is None:
            self.upload_date = timezone.now()
        return super().save(*args, **kwargs)
    
    @property
    def get_gross_salary(self):
        benefits = self.benefits.all()
        gross_total = self.basic_salary + sum([i.amount for i in benefits])
        
        return gross_total
    
    @property
    def get_nett_salary(self):
        benefits = self.benefits.all()
        total_salary = self.basic_salary + sum([i.amount for i in benefits])
        nett_total = total_salary - self.get_total_deductions
        
        return nett_total

    @property
    def get_selected_benefits(self):
        benefits = sum([i.amount for i in self.benefits.all()])
        return benefits

    @property
    def get_selected_deductions(self):
        deductions = sum([i.amount for i in self.deductions.all()])
        return deductions
    
    @property
    def get_total_deductions(self):
        deductions = sum([i.amount for i in self.deductions.all()])
        total = (self.income_tax + self.uif_contribution) + deductions
        return total
    
    
    

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
    



    
    
    