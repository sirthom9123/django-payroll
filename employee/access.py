from django.db.models import Q

from company.models import Company
from employee.models import Employee

HR_GROUP = "HR"
PAYROLL_GROUP = "Payroll"
ORGANISATION_GROUPS = (HR_GROUP, PAYROLL_GROUP)


def group_names(user):
    if not user.is_authenticated:
        return set()
    cached = getattr(user, "_hr_group_names", None)
    if cached is None:
        cached = set(user.groups.values_list("name", flat=True))
        user._hr_group_names = cached
    return cached


def can_use_hr(user):
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return bool(group_names(user).intersection(ORGANISATION_GROUPS))


def can_edit_hr(user):
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return HR_GROUP in group_names(user)


def can_run_payroll(user):
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return PAYROLL_GROUP in group_names(user)


def visible_companies(user):
    if not user.is_authenticated:
        return Company.objects.none()
    if user.is_superuser:
        return Company.objects.all()
    return Company.objects.filter(
        Q(owner=user) | Q(owner__groups__name__in=ORGANISATION_GROUPS)
    ).distinct()


def visible_employees(user):
    if not user.is_authenticated:
        return Employee.objects.none()
    if user.is_superuser:
        return Employee.objects.all()
    return Employee.objects.filter(
        Q(company__in=visible_companies(user))
        | Q(created_by=user)
        | Q(company__isnull=True)
    ).distinct()
