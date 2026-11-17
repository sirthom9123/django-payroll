import re

from django import forms
from django.db.models import Q

from company.models import Company
from employee.access import visible_companies
from employee.models import (
    Contract,
    Employee,
    EmployeeDocument,
    EmploymentHistory,
    Qualification,
)

DATE_INPUT = forms.DateInput(attrs={"type": "date"})


def designation_label(designation):
    department = designation.department.name if designation.department_id else ""
    if department and designation.name:
        return f"{designation.name} ({department})"
    return designation.name or ""


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "company",
            "emp_code",
            "first_name",
            "middle_name",
            "last_name",
            "maiden_name",
            "id_number",
            "passport",
            "email_address",
            "phone",
            "alt_phone",
            "address",
            "country",
            "city",
            "postal_code",
            "designation",
            "date_hired",
            "date_departed",
            "pension_number",
            "employee_type",
            "status",
        ]
        labels = {
            "company": "Company",
            "emp_code": "Employee code",
            "first_name": "First name",
            "middle_name": "Middle name",
            "last_name": "Last name",
            "maiden_name": "Maiden name",
            "id_number": "ID number",
            "passport": "Passport number",
            "email_address": "Email",
            "phone": "Phone",
            "alt_phone": "Alternate phone",
            "address": "Home address",
            "country": "Country",
            "city": "City",
            "postal_code": "Postal code",
            "designation": "Designation",
            "date_hired": "Date hired",
            "date_departed": "Date departed",
            "pension_number": "Pension number",
            "employee_type": "Employment type",
            "status": "Status",
        }
        help_texts = {
            "emp_code": "Leave blank to generate a code.",
            "id_number": "Enter a 13-digit South African ID number, or a passport number.",
        }
        widgets = {
            "date_hired": DATE_INPUT,
            "date_departed": DATE_INPUT,
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        from employee.models import Designation

        allowed = Q(pk__in=visible_companies(user).values("pk"))
        if self.instance.pk and self.instance.company_id:
            allowed = allowed | Q(pk=self.instance.company_id)
        self.fields["company"].queryset = Company.objects.filter(allowed).order_by("company_name")
        self.fields["company"].required = True
        self.fields["id_number"].required = False
        self.fields["passport"].required = False
        self.fields["emp_code"].required = False
        self.fields["designation"].queryset = Designation.objects.select_related("department").order_by("name")
        self.fields["designation"].label_from_instance = designation_label

    def clean(self):
        cleaned = super().clean()
        id_number = (cleaned.get("id_number") or "").strip()
        passport = (cleaned.get("passport") or "").strip()
        code = (cleaned.get("emp_code") or "").strip()
        if id_number and not re.fullmatch(r"\d{13}", id_number):
            self.add_error(
                "id_number",
                "Enter a 13-digit South African ID number, or a passport number.",
            )
        elif not id_number and not passport:
            self.add_error(
                "id_number",
                "Enter a 13-digit South African ID number, or a passport number.",
            )
        if code:
            existing = Employee.objects.filter(emp_code=code)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error("emp_code", "This employee code is already in use.")
        cleaned["id_number"] = id_number
        cleaned["passport"] = passport
        cleaned["emp_code"] = code
        return cleaned


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = [
            "contract_type",
            "start_date",
            "end_date",
            "job_title",
            "job_description",
            "notice_period_days",
            "signed_date",
        ]
        labels = {
            "contract_type": "Contract type",
            "start_date": "Start date",
            "end_date": "End date",
            "job_title": "Job title",
            "job_description": "Job description",
            "notice_period_days": "Notice period (days)",
            "signed_date": "Signed date",
        }
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "signed_date": DATE_INPUT,
            "job_description": forms.Textarea(attrs={"rows": 4}),
        }


class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = ["institution", "name", "year_completed", "nqf_level"]
        labels = {
            "institution": "Institution",
            "name": "Qualification",
            "year_completed": "Year completed",
            "nqf_level": "NQF level",
        }


class EmploymentHistoryForm(forms.ModelForm):
    class Meta:
        model = EmploymentHistory
        fields = ["employer", "role", "start_date", "end_date", "reason_for_leaving"]
        labels = {
            "employer": "Employer",
            "role": "Role",
            "start_date": "Start date",
            "end_date": "End date",
            "reason_for_leaving": "Reason for leaving",
        }
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "reason_for_leaving": forms.Textarea(attrs={"rows": 3}),
        }


class EmployeeDocumentForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ["title", "document_type", "file"]
        labels = {
            "title": "Title",
            "document_type": "Type",
            "file": "File",
        }
