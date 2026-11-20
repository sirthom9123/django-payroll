from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from employee.access import visible_companies, visible_employees
from leave.models import AttendanceStatus, LeaveApplication, LeaveKind, LeaveType


class LeaveTypeSelect(forms.Select):
    def __init__(self, *args, kinds=None, **kwargs):
        self.kinds = kinds or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        kind = self.kinds.get(str(getattr(value, "value", value)))
        if kind:
            option["attrs"]["data-kind"] = kind
        return option


class LeaveApplicationForm(forms.ModelForm):
    class Meta:
        model = LeaveApplication
        fields = ["employee", "leave_type", "start_date", "end_date", "reason", "other_parent_employed", "proof"]
        widgets = {
            "leave_type": LeaveTypeSelect(),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "employee": "Employee",
            "leave_type": "Leave type",
            "start_date": "Start date",
            "end_date": "End date",
            "reason": "Reason",
            "other_parent_employed": "Other parent employed",
            "proof": "Proof",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = visible_employees(user).order_by("last_name", "first_name")
        self.fields["employee"].label_from_instance = lambda obj: obj.get_full_name()
        self.fields["start_date"].help_text = "Monday to Friday. A public holiday inside annual leave is not deducted."
        self.fields["other_parent_employed"].required = False
        self.fields["other_parent_employed"].label = "Other parent employed"
        self.fields["other_parent_employed"].help_text = "Maternity and parental leave only."
        for name in ("start_date", "end_date"):
            self.fields[name].localize = False
            self.fields[name].input_formats = ["%Y-%m-%d"]
            self.fields[name].widget.format = "%Y-%m-%d"
        employee_id = self._selected_employee_id()
        types = LeaveType.objects.filter(company__in=visible_companies(user))
        if employee_id:
            types = types.filter(company__employees__pk=employee_id)
        self.fields["leave_type"].queryset = types.order_by("name")
        self.fields["leave_type"].label_from_instance = lambda obj: obj.name
        self.fields["leave_type"].widget.kinds = {
            str(item.pk): item.kind for item in self.fields["leave_type"].queryset
        }
        if self._selected_leave_kind() not in (LeaveKind.MATERNITY, LeaveKind.PARENTAL):
            self.fields["other_parent_employed"].widget.attrs["disabled"] = True

    def _selected_employee_id(self):
        if self.is_bound:
            raw = self.data.get(self.add_prefix("employee"))
        elif self.instance.pk:
            return self.instance.employee_id
        else:
            raw = self.initial.get("employee")
        if raw in (None, ""):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _selected_leave_kind(self):
        raw = None
        if self.is_bound:
            raw = self.data.get(self.add_prefix("leave_type"))
        elif getattr(self.instance, "leave_type_id", None):
            return self.instance.leave_type.kind
        else:
            raw = self.initial.get("leave_type")
        if raw in (None, ""):
            return None
        try:
            pk = int(getattr(raw, "pk", raw))
        except (TypeError, ValueError):
            return None
        match = self.fields["leave_type"].queryset.filter(pk=pk).first()
        return match.kind if match else None

    def clean(self):
        cleaned = super().clean()
        leave_type = cleaned.get("leave_type")
        employee = cleaned.get("employee")
        if leave_type is None or leave_type.kind not in (LeaveKind.MATERNITY, LeaveKind.PARENTAL):
            cleaned["other_parent_employed"] = None
        if (
            leave_type
            and employee
            and leave_type.kind == LeaveKind.FAMILY
            and cleaned.get("start_date")
            and cleaned.get("end_date")
        ):
            from leave.balance import _family_leave_error

            application = LeaveApplication(
                employee=employee,
                leave_type=leave_type,
                start_date=cleaned["start_date"],
                end_date=cleaned["end_date"],
            )
            if getattr(self.instance, "pk", None):
                application.pk = self.instance.pk
            message = _family_leave_error(application)
            if message:
                raise ValidationError({"employee": message})
        return cleaned


class AttendanceRowForm(forms.Form):
    employee_id = forms.IntegerField(widget=forms.HiddenInput)
    status = forms.ChoiceField(
        choices=[("", "Select status")] + list(AttendanceStatus.choices),
        label="Status",
        error_messages={"required": "Select a status."},
    )
    hours_worked = forms.DecimalField(
        label="Hours worked",
        max_digits=4,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("24"),
        error_messages={
            "required": "Enter the hours worked.",
            "invalid": "Enter hours as a number.",
            "min_value": "Hours worked cannot be negative.",
            "max_value": "Hours worked cannot be more than 24.",
        },
    )

    def __init__(self, *args, allowed_ids=None, **kwargs):
        self.allowed_ids = allowed_ids or set()
        super().__init__(*args, **kwargs)

    def clean_employee_id(self):
        value = self.cleaned_data["employee_id"]
        if value not in self.allowed_ids:
            raise ValidationError("That employee is not on your list.")
        return value


class BaseAttendanceFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            employee_id = form.cleaned_data.get("employee_id")
            if employee_id in seen:
                raise ValidationError("Each employee can have one row on this date.")
            seen.add(employee_id)


AttendanceFormSet = forms.formset_factory(AttendanceRowForm, formset=BaseAttendanceFormSet, extra=0)
