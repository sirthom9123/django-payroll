from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from employee.models import hr_document_storage


class LeaveKind(models.TextChoices):
    ANNUAL = "annual", "Annual"
    SICK = "sick", "Sick"
    FAMILY = "family", "Family responsibility"
    MATERNITY = "maternity", "Maternity"
    PARENTAL = "parental", "Parental"
    STUDY = "study", "Study"
    UNPAID = "unpaid", "Unpaid"


class AnnualAccrual(models.TextChoices):
    CYCLE = "cycle", "15 working days over the leave cycle"
    PER_17 = "per_17", "1 day for every 17 days worked or paid"


class LeaveStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Declined"
    CANCELLED = "cancelled", "Cancelled"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LEAVE = "leave", "Leave"
    PUBLIC_HOLIDAY = "public_holiday", "Public holiday"


LEAVE_KIND_DEFAULTS = (
    (LeaveKind.ANNUAL, "Annual leave", Decimal("15.00")),
    (LeaveKind.SICK, "Sick leave", Decimal("30.00")),
    (LeaveKind.FAMILY, "Family responsibility leave", Decimal("3.00")),
    (LeaveKind.MATERNITY, "Maternity leave", Decimal("0.00")),
    (LeaveKind.PARENTAL, "Parental leave", Decimal("0.00")),
    (LeaveKind.STUDY, "Study leave", Decimal("0.00")),
    (LeaveKind.UNPAID, "Unpaid leave", Decimal("0.00")),
)


def leave_proof_path(instance, filename):
    return f"leave-proof/{instance.employee_id}/{filename}"


def seed_leave_types(company):
    for kind, name, allowance in LEAVE_KIND_DEFAULTS:
        LeaveType.objects.get_or_create(
            company=company,
            kind=kind,
            defaults={"name": name, "days_per_year": allowance},
        )


def ensure_leave_types(sender, instance, created, **kwargs):
    if created:
        seed_leave_types(instance)


class LeaveType(models.Model):
    """Cycle allowance for one company. The balance in leave.balance accumulates it."""

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="leave_types",
    )
    kind = models.CharField(max_length=20, choices=LeaveKind.choices)
    name = models.CharField(max_length=80)
    days_per_year = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Working-day allowance for the cycle. Annual leave starts at 15 and accumulates from the date hired, unless the company agrees the 1-day-per-17 method. Sick leave starts at 30 over 36 months. Family responsibility starts at 3. Study leave stays 0 until the company sets it.",
    )
    accrual = models.CharField(
        max_length=20,
        choices=AnnualAccrual.choices,
        default=AnnualAccrual.CYCLE,
        help_text="Annual leave only. The 1-day-per-17 method is by agreement. Other leave types ignore this.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "kind"], name="one_leave_kind_per_company"),
        ]

    def __str__(self):
        return self.name

    @property
    def allows_unpaid(self):
        return self.kind == LeaveKind.UNPAID


class LeaveApplication(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="leave_applications",
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"), editable=False)
    reason = models.TextField()
    other_parent_employed = models.BooleanField(
        null=True,
        blank=True,
        help_text="Parental leave only. Yes: both parents are employed and share 4 months and 10 days. No: this employee is the only employed parent and gets 4 consecutive months.",
    )
    proof = models.FileField(
        upload_to=leave_proof_path,
        storage=hr_document_storage,
        blank=True,
        help_text="Optional. For a sick note or other proof.",
    )
    status = models.CharField(max_length=20, choices=LeaveStatus.choices, default=LeaveStatus.DRAFT)
    decision_note = models.TextField(blank=True)
    captured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_captured",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["status", "start_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="leave_end_on_or_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.employee} — {self.leave_type} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        from leave.balance import validate_application

        validate_application(self)

    @property
    def can_cancel(self):
        return self.status in (LeaveStatus.DRAFT, LeaveStatus.SUBMITTED, LeaveStatus.APPROVED)


class Attendance(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_rows",
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    hours_worked = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_recorded",
    )

    class Meta:
        ordering = ["-date", "employee_id"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="one_attendance_row_per_day"),
            models.CheckConstraint(
                check=models.Q(hours_worked__gte=0) & models.Q(hours_worked__lte=24),
                name="attendance_hours_within_a_day",
            ),
        ]

    def __str__(self):
        return f"{self.employee} {self.date} {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.hours_worked is not None and (self.hours_worked < 0 or self.hours_worked > 24):
            raise ValidationError({"hours_worked": "Hours worked cannot be more than 24."})
