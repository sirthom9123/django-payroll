import re
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class AgreementStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    CLOSED = "closed", "Closed"


class PlanOutcome(models.TextChoices):
    OPEN = "open", "Open"
    IMPROVED = "improved", "Improved"
    NOT_IMPROVED = "not_improved", "Not improved"


class DevelopmentStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In progress"
    DONE = "done", "Done"


_CYCLE = re.compile(r"^(\d{4})/(\d{2})$")
_WEIGHT = [
    MinValueValidator(1, message="Enter a weight from 1 to 100."),
    MaxValueValidator(100, message="Enter a weight from 1 to 100."),
]
_SCORE = [
    MinValueValidator(1, message="Enter a score from 1 to 5."),
    MaxValueValidator(5, message="Enter a score from 1 to 5."),
]
_LEVEL = [
    MinValueValidator(1, message="Enter a level from 1 to 5."),
    MaxValueValidator(5, message="Enter a level from 1 to 5."),
]


def parse_cycle(value):
    match = _CYCLE.match((value or "").strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end != (start + 1) % 100:
        return None
    return f"{start}/{end:02d}"


class Agreement(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="performance_agreements",
    )
    cycle = models.CharField(max_length=7, help_text="For example 2026/27.")
    status = models.CharField(
        max_length=20,
        choices=AgreementStatus.choices,
        default=AgreementStatus.DRAFT,
    )
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="performance_agreements_filed",
    )

    class Meta:
        ordering = ["-cycle", "employee__last_name", "employee__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "cycle"],
                name="one_agreement_per_employee_cycle",
                violation_error_message="This employee already has an agreement for this cycle.",
            ),
        ]

    def __str__(self):
        return f"{self.employee} — {self.cycle}"

    def unique_error_message(self, model_class, unique_check):
        if tuple(unique_check) == ("employee", "cycle"):
            return "This employee already has an agreement for this cycle."
        return super().unique_error_message(model_class, unique_check)

    def clean(self):
        super().clean()
        normalised = parse_cycle(self.cycle)
        if normalised is None:
            raise ValidationError({"cycle": "Enter the cycle as 2026/27."})
        self.cycle = normalised
        if self.pk:
            previous = Agreement.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous == AgreementStatus.CLOSED and self.status != AgreementStatus.CLOSED:
                raise ValidationError({"status": "A closed agreement cannot be reopened."})
            if (
                previous == AgreementStatus.ACTIVE
                and self.status == AgreementStatus.DRAFT
                and Appraisal.objects.filter(agreement_id=self.pk).exists()
            ):
                raise ValidationError({
                    "status": "This agreement has an appraisal. It cannot go back to draft.",
                })
        if self.status == AgreementStatus.ACTIVE:
            total = 0
            if self.pk:
                total = (
                    KeyPerformanceIndicator.objects.filter(kpa__agreement_id=self.pk)
                    .aggregate(total=Sum("weight"))["total"]
                    or 0
                )
            if total != 100:
                if total == 0:
                    raise ValidationError({
                        "status": (
                            "Add the indicators first. Their weights must add to 100 "
                            "before the agreement is active."
                        ),
                    })
                raise ValidationError({
                    "status": (
                        "KPI weights must add to 100 before the agreement is active. "
                        f"They add to {total}."
                    ),
                })

    def weight_total(self):
        if self.pk and "kpas" in getattr(self, "_prefetched_objects_cache", {}):
            total = 0
            for area in self.kpas.all():
                for indicator in area.kpis.all():
                    total += indicator.weight
            return total
        if not self.pk:
            return 0
        return (
            KeyPerformanceIndicator.objects.filter(kpa__agreement_id=self.pk)
            .aggregate(total=Sum("weight"))["total"]
            or 0
        )


class KeyPerformanceArea(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="kpas")
    name = models.CharField("Key performance area", max_length=120)

    class Meta:
        ordering = ["id"]
        verbose_name = "Key performance area"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.agreement_id:
            _structure_is_open(self.agreement)


class KeyPerformanceIndicator(models.Model):
    kpa = models.ForeignKey(KeyPerformanceArea, on_delete=models.CASCADE, related_name="kpis")
    name = models.CharField("Key performance indicator", max_length=120)
    measure = models.CharField(max_length=200)
    weight = models.PositiveSmallIntegerField(validators=_WEIGHT)

    class Meta:
        ordering = ["id"]
        verbose_name = "Key performance indicator"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.kpa_id or self.weight is None:
            return
        _structure_is_open(self.kpa.agreement)
        others = KeyPerformanceIndicator.objects.filter(kpa__agreement_id=self.kpa.agreement_id)
        if self.pk:
            others = others.exclude(pk=self.pk)
        total = (others.aggregate(total=Sum("weight"))["total"] or 0) + self.weight
        if total > 100:
            raise ValidationError({
                "weight": f"KPI weights cannot add to more than 100. They add to {total}.",
            })


class Appraisal(models.Model):
    agreement = models.OneToOneField(Agreement, on_delete=models.CASCADE, related_name="appraisal")
    appraisal_date = models.DateField("Appraisal date")
    overall_comment = models.TextField("Overall comment")
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appraisals_filed",
    )

    class Meta:
        ordering = ["-appraisal_date"]

    def __str__(self):
        return f"Appraisal {self.agreement.cycle}"

    def clean(self):
        super().clean()
        if self.agreement_id and self.agreement.status != AgreementStatus.ACTIVE:
            raise ValidationError("File the appraisal only when the agreement is active.")
        if self.appraisal_date and self.appraisal_date > timezone.localdate():
            raise ValidationError({"appraisal_date": "The appraisal date cannot be in the future."})

    def overall_score(self):
        weighted = Decimal("0")
        total_weight = 0
        for row in self.scores.all():
            total_weight += row.kpi.weight
            weighted += Decimal(row.score) * Decimal(row.kpi.weight)
        if total_weight != 100:
            return None
        return (weighted / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AppraisalScore(models.Model):
    appraisal = models.ForeignKey(Appraisal, on_delete=models.CASCADE, related_name="scores")
    kpi = models.ForeignKey(KeyPerformanceIndicator, on_delete=models.CASCADE, related_name="scores")
    score = models.PositiveSmallIntegerField(validators=_SCORE)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["kpi_id"]
        constraints = [
            models.UniqueConstraint(fields=["appraisal", "kpi"], name="one_score_per_kpi"),
        ]

    def __str__(self):
        return f"{self.kpi} — {self.score}"


class ImprovementPlan(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="improvement_plans",
    )
    start_date = models.DateField("Start date")
    review_date = models.DateField("Review date")
    concern = models.TextField()
    actions = models.TextField()
    outcome = models.CharField(max_length=20, choices=PlanOutcome.choices, default=PlanOutcome.OPEN)
    outcome_note = models.TextField("Outcome note", blank=True)
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="improvement_plans_filed",
    )

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [models.Index(fields=["employee", "outcome"])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(review_date__gte=models.F("start_date")),
                name="pip_review_on_or_after_start",
                violation_error_message="The review date must be on or after the start date.",
            ),
        ]

    def __str__(self):
        return f"{self.employee} — {self.get_outcome_display()}"

    def clean(self):
        super().clean()
        if self.start_date and self.review_date and self.review_date < self.start_date:
            raise ValidationError({
                "review_date": "The review date must be on or after the start date.",
            })


class SkillAssessment(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="skill_assessments",
    )
    skill = models.CharField(max_length=120)
    level = models.PositiveSmallIntegerField(validators=_LEVEL)
    assessed_on = models.DateField("Date")
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="skill_assessments_filed",
    )

    class Meta:
        ordering = ["-assessed_on", "-id"]
        indexes = [models.Index(fields=["employee", "skill"])]

    def __str__(self):
        return f"{self.skill} — {self.level}"

    def clean(self):
        super().clean()
        if self.assessed_on and self.assessed_on > timezone.localdate():
            raise ValidationError({"assessed_on": "The assessment date cannot be in the future."})


class DevelopmentPlan(models.Model):
    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="development_plans",
    )
    skill_gap = models.CharField("Skill gap", max_length=200)
    action = models.TextField()
    due_date = models.DateField("Due date")
    status = models.CharField(
        max_length=20,
        choices=DevelopmentStatus.choices,
        default=DevelopmentStatus.PLANNED,
    )
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="development_plans_filed",
    )

    class Meta:
        ordering = ["due_date", "id"]
        indexes = [models.Index(fields=["employee", "status"])]
        verbose_name = "Development plan"

    def __str__(self):
        return self.skill_gap


def _structure_is_open(agreement):
    if agreement.status == AgreementStatus.CLOSED:
        raise ValidationError("A closed agreement cannot be changed.")
    if agreement.status != AgreementStatus.DRAFT:
        raise ValidationError("KPAs and KPIs can be changed only while the agreement is a draft.")
