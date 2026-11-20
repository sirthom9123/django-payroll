import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from employee.models import Employee, EmployeeType, Status


class VacancyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class ApplicationStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    SHORTLISTED = "shortlisted", "Shortlisted"
    OFFERED = "offered", "Offered"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"
    HIRED = "hired", "Hired"


class Vacancy(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="vacancies",
    )
    designation = models.ForeignKey(
        "employee.Designation",
        on_delete=models.PROTECT,
        related_name="vacancies",
    )
    title = models.CharField(max_length=150)
    description = models.TextField()
    openings = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    closing_date = models.DateField("Closing date", null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=VacancyStatus.choices,
        default=VacancyStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vacancies_opened",
    )

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Vacancies"
        constraints = [
            models.CheckConstraint(
                check=models.Q(openings__gte=1),
                name="vacancy_has_an_opening",
                violation_error_message="Enter at least one opening.",
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.pk:
            previous = Vacancy.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous == VacancyStatus.CLOSED and self.status != VacancyStatus.CLOSED:
                raise ValidationError({"status": "A closed vacancy cannot be reopened."})
        if self.status == VacancyStatus.OPEN and self.closing_date and self.closing_date < timezone.localdate():
            raise ValidationError({
                "closing_date": "The closing date has passed. Choose a later date or close the vacancy.",
            })
        if self.pk and self.openings is not None:
            hired = self.applications.filter(status=ApplicationStatus.HIRED).count()
            if self.openings < hired:
                raise ValidationError({
                    "openings": "Openings cannot be fewer than the people already hired.",
                })

    def hired_count(self):
        if self.pk and "applications" in getattr(self, "_prefetched_objects_cache", {}):
            return sum(1 for row in self.applications.all() if row.status == ApplicationStatus.HIRED)
        if not self.pk:
            return 0
        return self.applications.filter(status=ApplicationStatus.HIRED).count()


class Application(models.Model):
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="applications")
    first_name = models.CharField("First name", max_length=150)
    last_name = models.CharField("Last name", max_length=150)
    email = models.EmailField("Email")
    phone = models.CharField("Phone", max_length=50)
    id_number = models.CharField("ID number", max_length=13, blank=True)
    passport = models.CharField("Passport number", max_length=150, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.RECEIVED,
    )
    note = models.TextField(blank=True)
    applied_on = models.DateField("Application date")
    employee = models.OneToOneField(
        "employee.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recruitment_application",
    )
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications_filed",
    )

    class Meta:
        ordering = ["-applied_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vacancy", "email"],
                name="one_application_per_vacancy_email",
                violation_error_message="This person has already applied for this vacancy.",
            ),
            models.UniqueConstraint(
                fields=["vacancy", "id_number"],
                condition=~models.Q(id_number=""),
                name="one_application_per_vacancy_id",
                violation_error_message="This person has already applied for this vacancy.",
            ),
            models.UniqueConstraint(
                fields=["vacancy", "passport"],
                condition=~models.Q(passport=""),
                name="one_application_per_vacancy_passport",
                violation_error_message="This person has already applied for this vacancy.",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        super().clean()
        self.email = (self.email or "").strip().lower()
        self.id_number = (self.id_number or "").strip()
        self.passport = (self.passport or "").strip().upper()
        self.note = (self.note or "").strip()
        if self.id_number and not re.fullmatch(r"\d{13}", self.id_number):
            raise ValidationError({
                "id_number": "Enter a 13-digit South African ID number, or a passport number.",
            })
        if not self.id_number and not self.passport:
            raise ValidationError({
                "id_number": "Enter a 13-digit South African ID number, or a passport number.",
            })
        if self.applied_on and self.applied_on > timezone.localdate():
            raise ValidationError({"applied_on": "The application date cannot be in the future."})
        if self.status == ApplicationStatus.DECLINED and not self.note:
            raise ValidationError({"note": "A decline needs a note."})
        if not self.vacancy_id:
            return
        vacancy = self.vacancy
        if self.pk:
            previous = (
                Application.objects.filter(pk=self.pk)
                .values("status", "employee_id")
                .first()
            )
            if previous and previous["status"] == ApplicationStatus.HIRED:
                if self.status != ApplicationStatus.HIRED or self.employee_id != previous["employee_id"]:
                    raise ValidationError("A hired application cannot be changed.")
        else:
            if vacancy.status != VacancyStatus.OPEN:
                raise ValidationError("Add an application only while the vacancy is open.")
            if vacancy.closing_date and vacancy.closing_date < timezone.localdate():
                raise ValidationError("This vacancy has closed.")
        if self.status == ApplicationStatus.HIRED and not self.employee_id:
            raise ValidationError("Hire this person from the application page.")
        self._reject_duplicate()

    def _reject_duplicate(self):
        if not self.vacancy_id:
            return
        others = Application.objects.filter(vacancy_id=self.vacancy_id)
        if self.pk:
            others = others.exclude(pk=self.pk)
        if self.email and others.filter(email__iexact=self.email).exists():
            raise ValidationError({
                "email": "This person has already applied for this vacancy.",
            })
        if self.id_number and others.filter(id_number=self.id_number).exists():
            raise ValidationError({
                "id_number": "This person has already applied for this vacancy.",
            })
        if self.passport and others.filter(passport__iexact=self.passport).exists():
            raise ValidationError({
                "passport": "This person has already applied for this vacancy.",
            })

    def hire(self, user, *, address, country, city, postal_code, date_hired):
        with transaction.atomic():
            application = (
                Application.objects.select_for_update()
                .select_related("vacancy", "vacancy__company", "vacancy__designation")
                .get(pk=self.pk)
            )
            vacancy = Vacancy.objects.select_for_update().get(pk=application.vacancy_id)
            if application.employee_id or application.status == ApplicationStatus.HIRED:
                raise ValidationError("This person has already been hired.")
            if application.status != ApplicationStatus.OFFERED:
                raise ValidationError("Offer the job before you hire this person.")
            if vacancy.status != VacancyStatus.OPEN:
                raise ValidationError("Hire someone only while the vacancy is open.")
            if vacancy.hired_count() >= vacancy.openings:
                raise ValidationError("This vacancy has no openings left.")
            _identity_is_new(application)
            employee = Employee(
                first_name=application.first_name,
                last_name=application.last_name,
                email_address=application.email,
                phone=application.phone,
                id_number=application.id_number,
                passport=application.passport,
                address=address,
                country=country,
                city=city,
                postal_code=postal_code,
                date_hired=date_hired,
                company=vacancy.company,
                designation=vacancy.designation,
                employee_type=EmployeeType.FULL_TIME,
                status=Status.ACTIVE,
                created_by=user,
            )
            exclude = []
            if not application.id_number:
                exclude.append("id_number")
            employee.full_clean(exclude=exclude)
            employee.save()
            application.employee = employee
            application.status = ApplicationStatus.HIRED
            application.full_clean()
            application.save()
            hired = vacancy.applications.filter(status=ApplicationStatus.HIRED).count()
            if hired >= vacancy.openings and vacancy.status != VacancyStatus.CLOSED:
                vacancy.status = VacancyStatus.CLOSED
                vacancy.save()
            return employee


def _identity_is_new(application):
    if application.id_number and Employee.objects.filter(id_number=application.id_number).exists():
        raise ValidationError("This ID number is already on an employee file.")
    if application.passport and Employee.objects.filter(passport__iexact=application.passport).exists():
        raise ValidationError("This passport number is already on an employee file.")
