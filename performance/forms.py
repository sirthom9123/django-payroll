from django import forms

from employee.access import visible_employees
from performance.models import (
    Agreement,
    DevelopmentPlan,
    ImprovementPlan,
    KeyPerformanceArea,
    KeyPerformanceIndicator,
    SkillAssessment,
)


def limit_employee(form, user):
    form.fields["employee"].queryset = visible_employees(user).order_by("last_name", "first_name")
    form.fields["employee"].label_from_instance = lambda obj: obj.get_full_name()


def use_date_input(field):
    field.widget = forms.DateInput(attrs={"type": "date"})
    field.localize = False
    field.input_formats = ["%Y-%m-%d"]
    field.widget.format = "%Y-%m-%d"


class AgreementForm(forms.ModelForm):
    class Meta:
        model = Agreement
        fields = ["employee", "cycle", "status"]
        labels = {
            "employee": "Employee",
            "cycle": "Cycle",
            "status": "Status",
        }
        help_texts = {
            "cycle": "For example 2026/27.",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        limit_employee(self, user)
        saved = self.instance.status if self.instance.pk else None
        if saved is None:
            self.fields["status"].choices = [("draft", "Draft")]
            self.fields["status"].help_text = (
                "Save this as a draft. On the next page, add the indicators. "
                "Set the status to Active once their weights add to 100."
            )
        else:
            self.fields["status"].help_text = (
                f"Weights add to {self.instance.weight_total()} of 100. "
                "The agreement can be active only when they add to 100."
            )
        if saved and saved != "draft":
            self.fields["employee"].disabled = True
            self.fields["cycle"].disabled = True


class KeyPerformanceAreaForm(forms.ModelForm):
    class Meta:
        model = KeyPerformanceArea
        fields = ["name"]
        labels = {"name": "Key performance area"}


class KeyPerformanceIndicatorForm(forms.ModelForm):
    class Meta:
        model = KeyPerformanceIndicator
        fields = ["name", "measure", "weight"]
        labels = {
            "name": "Key performance indicator",
            "measure": "Measure",
            "weight": "Weight",
        }
        help_texts = {
            "measure": "How this indicator is judged.",
            "weight": "A whole number from 1 to 100. All indicators on the agreement must add to 100.",
        }


class AppraisalForm(forms.Form):
    appraisal_date = forms.DateField(
        label="Appraisal date",
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    overall_comment = forms.CharField(
        label="Overall comment",
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"required": "Enter an overall comment."},
    )

    def __init__(self, *args, kpis, **kwargs):
        super().__init__(*args, **kwargs)
        use_date_input(self.fields["appraisal_date"])
        self.kpis = list(kpis)
        score_names = []
        for kpi in self.kpis:
            score_name = f"score_{kpi.pk}"
            comment_name = f"comment_{kpi.pk}"
            self.fields[score_name] = forms.IntegerField(
                label=f"Score for {kpi.name}",
                min_value=1,
                max_value=5,
                help_text=f"{kpi.kpa.name}. Weight {kpi.weight}. Measure: {kpi.measure}.",
                error_messages={
                    "required": "Enter a score from 1 to 5.",
                    "invalid": "Enter a score from 1 to 5.",
                    "min_value": "Enter a score from 1 to 5.",
                    "max_value": "Enter a score from 1 to 5.",
                },
            )
            self.fields[comment_name] = forms.CharField(
                label=f"Comment for {kpi.name}",
                required=False,
                widget=forms.Textarea(attrs={"rows": 2}),
            )
            score_names.extend([score_name, comment_name])
        self.order_fields(["appraisal_date", *score_names, "overall_comment"])

    def clean(self):
        from django.utils import timezone

        cleaned = super().clean()
        day = cleaned.get("appraisal_date")
        if day and day > timezone.localdate():
            self.add_error("appraisal_date", "The appraisal date cannot be in the future.")
        return cleaned


class ImprovementPlanForm(forms.ModelForm):
    class Meta:
        model = ImprovementPlan
        fields = ["employee", "start_date", "review_date", "concern", "actions", "outcome", "outcome_note"]
        widgets = {
            "concern": forms.Textarea(attrs={"rows": 4}),
            "actions": forms.Textarea(attrs={"rows": 4}),
            "outcome_note": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "employee": "Employee",
            "start_date": "Start date",
            "review_date": "Review date",
            "concern": "Concern",
            "actions": "Actions",
            "outcome": "Outcome",
            "outcome_note": "Outcome note",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        limit_employee(self, user)
        use_date_input(self.fields["start_date"])
        use_date_input(self.fields["review_date"])


class SkillAssessmentForm(forms.ModelForm):
    class Meta:
        model = SkillAssessment
        fields = ["employee", "skill", "level", "assessed_on"]
        labels = {
            "employee": "Employee",
            "skill": "Skill",
            "level": "Level",
            "assessed_on": "Date",
        }
        help_texts = {"level": "1 is the lowest and 5 is the highest."}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        limit_employee(self, user)
        use_date_input(self.fields["assessed_on"])


class DevelopmentPlanForm(forms.ModelForm):
    class Meta:
        model = DevelopmentPlan
        fields = ["employee", "skill_gap", "action", "due_date", "status"]
        widgets = {"action": forms.Textarea(attrs={"rows": 4})}
        labels = {
            "employee": "Employee",
            "skill_gap": "Skill gap",
            "action": "Action",
            "due_date": "Due date",
            "status": "Status",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        limit_employee(self, user)
        use_date_input(self.fields["due_date"])
