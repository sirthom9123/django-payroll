import re
from decimal import Decimal

from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from company.models import Company
from employee.access import visible_companies, visible_employees
from employee.models import (
    AllowanceLine,
    Contract,
    DeductionLine,
    Employee,
    EmployeeDocument,
    EmploymentHistory,
    Payroll,
    PayrollPayment,
    Qualification,
    Status,
    TaxBand,
    TaxYear,
)
from employee.payroll_math import BASIC_SALARY_LIMIT, basic_salary, money

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
            "date_of_birth",
            "designation",
            "gross_salary",
            "hourly_rate",
            "date_hired",
            "days_per_week",
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
            "date_of_birth": "Date of birth",
            "designation": "Designation",
            "date_hired": "Date hired",
            "days_per_week": "Days per week",
            "date_departed": "Date departed",
            "gross_salary": "Gross salary (ZAR)",
            "hourly_rate": "Hourly rate (ZAR)",
            "pension_number": "Pension number",
            "employee_type": "Employment type",
            "status": "Status",
        }
        help_texts = {
            "emp_code": "Leave blank to generate a code.",
            "id_number": "Enter a 13-digit South African ID number, or a passport number.",
            "date_of_birth": "Used for the PAYE age rebate. Leave blank to apply only the primary rebate.",
            "gross_salary": "Monthly package for full-time, part-time, and intern staff. A permanent contract always uses this figure.",
            "hourly_rate": "Used when the employment type is Contract and the current contract is not permanent.",
            "days_per_week": "Used for family responsibility leave and annual-leave public holidays. Full-time staff usually work 5 days.",
        }
        widgets = {
            "date_of_birth": DATE_INPUT,
            "date_hired": DATE_INPUT,
            "date_departed": DATE_INPUT,
            "days_per_week": forms.NumberInput(attrs={"min": "1", "max": "7", "step": "1"}),
            "gross_salary": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
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


MONEY = forms.NumberInput(attrs={"step": "0.01", "min": "0.00"})


class DaysPerWeekForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["days_per_week"]
        labels = {"days_per_week": "Days per week"}
        help_texts = {
            "days_per_week": "Family responsibility leave needs at least 4. Full-time staff usually work 5.",
        }
        widgets = {
            "days_per_week": forms.NumberInput(attrs={"min": "1", "max": "7", "step": "1"}),
        }


class GrossSalaryForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["gross_salary", "hourly_rate"]
        labels = {
            "gross_salary": "Gross salary (ZAR)",
            "hourly_rate": "Hourly rate (ZAR)",
        }
        help_texts = {
            "gross_salary": "Monthly package. A new payroll run fills this in and keeps it locked.",
            "hourly_rate": "Consultant rate. A new payroll run fills this in and keeps it locked.",
        }
        widgets = {
            "gross_salary": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }


class PayrollRunForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = [
            "employee",
            "start_date",
            "end_date",
            "rate",
            "hours",
            "overtime_hours",
            "overtime_rate",
        ]
        labels = {
            "employee": "Employee",
            "start_date": "Period start",
            "end_date": "Period end",
            "rate": "Rate (ZAR)",
            "hours": "Ordinary hours",
            "overtime_hours": "Overtime hours",
            "overtime_rate": "Overtime rate (ZAR)",
        }
        help_texts = {
            "rate": "Leave blank to use the employee’s monthly gross salary.",
            "hours": "Used only with a rate. Basic salary is then the rate times these hours.",
            "overtime_hours": "Leave at 0 if there is no overtime.",
            "overtime_rate": "Used only when overtime hours are more than zero.",
        }
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "hours": MONEY,
            "overtime_hours": MONEY,
            "overtime_rate": MONEY,
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        employees = (
            visible_employees(user)
            .select_related("designation")
            .prefetch_related("contracts")
            .order_by("last_name", "first_name")
        )
        if self.instance.pk and self.instance.employee_id:
            employees = (employees | Employee.objects.filter(pk=self.instance.employee_id)).distinct()
        self.fields["employee"].queryset = employees
        self.fields["employee"].label_from_instance = (
            lambda employee: f"{employee.get_full_name()} ({employee.emp_code})"
        )
        for name in ("employee", "start_date", "end_date"):
            self.fields[name].required = True
        self.fields["rate"].required = False
        self.fields["hours"].required = False
        self.fields["overtime_hours"].required = False
        self.fields["overtime_rate"].required = False
        self.fields["gross_salary"] = forms.DecimalField(
            required=False,
            label="Gross salary (ZAR)",
            help_text="Filled from the employee file for salaried staff. It cannot be changed on this run.",
            min_value=Decimal("0.01"),
            widget=MONEY,
            disabled=True,
        )
        self.fields["rate"].disabled = True
        self.fields["rate"].help_text = "Filled from the consultant’s hourly rate. It cannot be changed on this run."
        self.order_fields([
            "employee",
            "gross_salary",
            "start_date",
            "end_date",
            "rate",
            "hours",
            "overtime_hours",
            "overtime_rate",
        ])
        if not self.is_bound and self.instance.employee_id:
            chosen = self.instance.employee
            if chosen.pay_basis() == "hourly":
                self.fields["rate"].initial = chosen.hourly_rate
            else:
                self.fields["gross_salary"].initial = chosen.gross_salary
        self.pay_people = [
            {
                "id": person.pk,
                "basis": person.pay_basis(),
                "gross": "" if person.gross_salary is None else str(person.gross_salary),
                "rate": "" if person.hourly_rate is None else str(person.hourly_rate),
            }
            for person in self.fields["employee"].queryset
        ]
        if not self.is_bound and not self.instance.pk:
            self.fields["overtime_hours"].initial = Decimal("0.00")
            self.fields["overtime_rate"].initial = Decimal("0.00")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        if start and TaxYear.for_date(start) is None:
            self.add_error(
                "start_date",
                "There is no PAYE table for this date. Add the tax year under PAYE tables.",
            )
        overtime_hours = cleaned.get("overtime_hours")
        overtime_rate = cleaned.get("overtime_rate")
        if overtime_hours is None:
            overtime_hours = Decimal("0.00")
            cleaned["overtime_hours"] = overtime_hours
        if overtime_rate is None:
            overtime_rate = Decimal("0.00")
            cleaned["overtime_rate"] = overtime_rate
        if overtime_hours < 0:
            self.add_error("overtime_hours", "Enter zero or more overtime hours.")
        if overtime_rate < 0:
            self.add_error("overtime_rate", "Enter zero or more for the overtime rate.")
        if overtime_hours > 0 and overtime_rate <= 0:
            self.add_error("overtime_rate", "Enter an overtime rate.")
        ordinary_hours = cleaned.get("hours")
        if ordinary_hours is None:
            ordinary_hours = Decimal("0.00")
            cleaned["hours"] = ordinary_hours
        if ordinary_hours < 0:
            self.add_error("hours", "Enter zero or more ordinary hours.")
        employee = cleaned.get("employee")
        if employee is None:
            return cleaned
        left = (
            employee.status == Status.RETIRED
            or (start and employee.date_departed and start >= employee.date_departed)
        )
        if left:
            self.add_error(
                "employee",
                "This employee has left or retired. Their pay is no longer used.",
            )
            return cleaned
        if employee.pay_basis() == "hourly":
            cleaned["gross_salary"] = None
            cleaned["rate"] = employee.hourly_rate
            if not employee.hourly_rate:
                self.add_error("employee", "Add an hourly rate on the employee file before running payroll.")
            elif ordinary_hours <= 0:
                self.add_error("hours", "Enter the ordinary hours for this rate.")
            elif basic_salary(employee.hourly_rate, ordinary_hours) > BASIC_SALARY_LIMIT:
                self.add_error("hours", "Basic salary from a rate cannot be more than R99,999.99.")
        else:
            cleaned["rate"] = None
            cleaned["hours"] = Decimal("0.00")
            cleaned["gross_salary"] = employee.gross_salary
            if not employee.gross_salary:
                self.add_error("employee", "Add a gross salary on the employee file before running payroll.")
        return cleaned


class _RunLineForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        name = (cleaned.get("name") or "").strip()
        amount = cleaned.get("amount")
        if not name and amount is None:
            return cleaned
        if name and amount is None:
            self.add_error("amount", "Enter an amount.")
        if amount is not None and not name:
            self.add_error("name", "Enter a name for this amount.")
        if name:
            cleaned["name"] = name
        return cleaned


class AllowanceLineForm(_RunLineForm):
    class Meta:
        model = AllowanceLine
        fields = ["name", "amount"]
        labels = {"name": "Allowance name", "amount": "Amount (ZAR)"}
        widgets = {"amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"})}


class DeductionLineForm(_RunLineForm):
    class Meta:
        model = DeductionLine
        fields = ["name", "amount"]
        labels = {"name": "Deduction name", "amount": "Amount (ZAR)"}
        widgets = {"amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"})}


AllowanceLineFormSet = inlineformset_factory(
    Payroll,
    AllowanceLine,
    form=AllowanceLineForm,
    extra=1,
    can_delete=True,
)

DeductionLineFormSet = inlineformset_factory(
    Payroll,
    DeductionLine,
    form=DeductionLineForm,
    extra=1,
    can_delete=True,
)


class PayrollPaymentForm(forms.ModelForm):
    class Meta:
        model = PayrollPayment
        fields = ["method", "payment_date", "reference", "amount"]
        labels = {
            "method": "Method",
            "payment_date": "Payment date",
            "reference": "Reference",
            "amount": "Amount (ZAR)",
        }
        widgets = {
            "payment_date": DATE_INPUT,
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }

    def __init__(self, *args, payroll, **kwargs):
        self.payroll = payroll
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = money(self.cleaned_data.get("amount"))
        nett = self.payroll.get_nett_salary
        if amount != nett:
            raise forms.ValidationError(f"Amount must equal the nett salary (R{nett:.2f}).")
        return amount


class PayrollReportForm(forms.Form):
    company = forms.ModelChoiceField(queryset=Company.objects.none(), label="Company")
    start_date = forms.DateField(label="Period start", widget=DATE_INPUT)
    end_date = forms.DateField(label="Period end", widget=DATE_INPUT)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = visible_companies(user).order_by("company_name")

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned


class TaxYearForm(forms.ModelForm):
    class Meta:
        model = TaxYear
        fields = [
            "name",
            "start_date",
            "end_date",
            "primary_rebate",
            "secondary_rebate",
            "tertiary_rebate",
        ]
        labels = {
            "name": "Tax year",
            "start_date": "Start date",
            "end_date": "End date",
            "primary_rebate": "Primary rebate (ZAR)",
            "secondary_rebate": "Secondary rebate, age 65 (ZAR)",
            "tertiary_rebate": "Tertiary rebate, age 75 (ZAR)",
        }
        help_texts = {
            "name": "For example, 2027/28.",
            "secondary_rebate": "Added when the employee is 65 or older on the last day of this tax year.",
            "tertiary_rebate": "Added as well when the employee is 75 or older on that day.",
        }
        widgets = {
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "primary_rebate": MONEY,
            "secondary_rebate": MONEY,
            "tertiary_rebate": MONEY,
        }


class TaxBandForm(forms.ModelForm):
    class Meta:
        model = TaxBand
        fields = ["income_from", "income_to", "rate_percent", "base_tax", "above_amount"]
        labels = {
            "income_from": "From (ZAR)",
            "income_to": "To (ZAR)",
            "rate_percent": "Rate (%)",
            "base_tax": "Base tax (ZAR)",
            "above_amount": "Above (ZAR)",
        }
        help_texts = {
            "income_to": "Leave blank on the top band only.",
        }
        widgets = {
            "income_from": MONEY,
            "income_to": MONEY,
            "rate_percent": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "max": "100"}),
            "base_tax": MONEY,
            "above_amount": MONEY,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["income_to"].required = False
        self.fields["base_tax"].required = False
        self.fields["above_amount"].required = False
        if not self.instance.pk:
            self.fields["base_tax"].initial = None
            self.fields["above_amount"].initial = None

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        income_from = cleaned.get("income_from")
        income_to = cleaned.get("income_to")
        if income_from is None and income_to is None and cleaned.get("rate_percent") is None:
            return cleaned
        if income_from is None:
            return cleaned
        if income_to is not None and income_to < income_from:
            self.add_error("income_to", "To must be on or above From.")
        if cleaned.get("base_tax") is None:
            cleaned["base_tax"] = Decimal("0.00")
        if cleaned.get("above_amount") is None:
            cleaned["above_amount"] = Decimal("0.00")
        return cleaned


class TaxBandFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(form.errors for form in self.forms):
            return
        rows = []
        for form in self.forms:
            cleaned = getattr(form, "cleaned_data", None)
            if not cleaned or cleaned.get("DELETE"):
                continue
            if cleaned.get("income_from") is None and cleaned.get("rate_percent") is None:
                continue
            rows.append(cleaned)
        if not rows:
            raise ValidationError("Add at least one PAYE band.")
        rows.sort(key=lambda row: row["income_from"])
        if rows[0]["income_from"] != 0:
            raise ValidationError("The first band must start at 0.")
        if rows[-1].get("income_to") is not None:
            raise ValidationError("The top band must have no upper amount.")
        for earlier, later in zip(rows, rows[1:]):
            if earlier.get("income_to") is None:
                raise ValidationError("Only the top band can have no upper amount.")
            if later["income_from"] != earlier["income_to"] + 1:
                raise ValidationError(
                    "Bands cannot overlap or leave a gap. The next band must start at the previous upper amount plus 1."
                )


TaxBandInlineFormSet = inlineformset_factory(
    TaxYear,
    TaxBand,
    form=TaxBandForm,
    formset=TaxBandFormSet,
    extra=1,
    can_delete=True,
)
