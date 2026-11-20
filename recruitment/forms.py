from django import forms

from employee.access import visible_companies
from employee.forms import designation_label
from employee.models import Designation
from recruitment.models import Application, ApplicationStatus, Vacancy


DATE_INPUT = forms.DateInput(attrs={"type": "date"})


class VacancyForm(forms.ModelForm):
    class Meta:
        model = Vacancy
        fields = [
            "company",
            "designation",
            "title",
            "description",
            "openings",
            "closing_date",
            "status",
        ]
        labels = {
            "company": "Company",
            "designation": "Designation",
            "title": "Job title",
            "description": "Job description",
            "openings": "Openings",
            "closing_date": "Closing date",
            "status": "Status",
        }
        help_texts = {
            "openings": "How many people this vacancy can hire.",
            "closing_date": "Leave blank if the vacancy has no closing date.",
            "status": "Applications can be added only while the vacancy is open.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "closing_date": DATE_INPUT,
            "openings": forms.NumberInput(attrs={"min": "1", "step": "1"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = visible_companies(user).order_by("company_name")
        self.fields["designation"].queryset = Designation.objects.select_related("department").order_by("name")
        self.fields["designation"].label_from_instance = designation_label
        self.fields["closing_date"].required = False


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "id_number",
            "passport",
            "applied_on",
            "status",
            "note",
        ]
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email",
            "phone": "Phone",
            "id_number": "ID number",
            "passport": "Passport number",
            "applied_on": "Application date",
            "status": "Status",
            "note": "Note",
        }
        help_texts = {
            "id_number": "Enter a 13-digit South African ID number, or a passport number.",
            "note": "A decline needs a note.",
        }
        widgets = {
            "applied_on": DATE_INPUT,
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, vacancy, **kwargs):
        self.vacancy = vacancy
        super().__init__(*args, **kwargs)
        self.fields["id_number"].required = False
        self.fields["passport"].required = False
        self.fields["note"].required = False
        filing = [
            choice for choice in ApplicationStatus.choices
            if choice[0] != ApplicationStatus.HIRED
        ]
        self.fields["status"].choices = filing

    def clean(self):
        self.instance.vacancy = self.vacancy
        return super().clean()

    def save(self, commit=True):
        self.instance.vacancy = self.vacancy
        return super().save(commit)


class HireForm(forms.Form):
    address = forms.CharField(
        label="Home address",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    country = forms.CharField(label="Country", initial="South Africa")
    city = forms.CharField(label="City")
    postal_code = forms.CharField(label="Postal code")
    date_hired = forms.DateField(
        label="Date hired",
        widget=DATE_INPUT,
        input_formats=["%Y-%m-%d"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_hired"].widget.format = "%Y-%m-%d"
