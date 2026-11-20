from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from employee.access import can_edit_hr, visible_companies
from employee.hr_views import hr_login_required
from recruitment.forms import ApplicationForm, HireForm, VacancyForm
from recruitment.models import Application, ApplicationStatus, Vacancy, VacancyStatus


def recruitment_editor_required(view):
    @hr_login_required
    def wrapped(request, *args, **kwargs):
        if not can_edit_hr(request.user):
            return render(request, "hr/recruitment_denied.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def visible_vacancies(user):
    return Vacancy.objects.filter(company__in=visible_companies(user)).select_related(
        "company",
        "designation__department",
        "created_by",
    )


def get_vacancy(user, pk):
    return get_object_or_404(
        visible_vacancies(user).prefetch_related("applications"),
        pk=pk,
    )


def visible_applications(user):
    return Application.objects.filter(vacancy__company__in=visible_companies(user)).select_related(
        "vacancy",
        "vacancy__company",
        "vacancy__designation",
        "employee",
        "filed_by",
    )


def get_application(user, pk):
    return get_object_or_404(visible_applications(user), pk=pk)


def remember_owner(record, user, field):
    if not getattr(record, f"{field}_id"):
        setattr(record, field, user)


@hr_login_required
def vacancy_list(request):
    vacancies = visible_vacancies(request.user).prefetch_related("applications")
    return render(request, "hr/vacancy_list.html", {"vacancies": vacancies})


@recruitment_editor_required
def vacancy_create(request):
    form = VacancyForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        vacancy = form.save(commit=False)
        remember_owner(vacancy, request.user, "created_by")
        vacancy.save()
        messages.success(request, "Vacancy saved.")
        return redirect("hr:vacancy_detail", pk=vacancy.pk)
    return render(request, "hr/vacancy_form.html", {
        "form": form,
        "heading": "New vacancy",
        "submit_label": "Save vacancy",
    })


@hr_login_required
def vacancy_detail(request, pk):
    vacancy = get_vacancy(request.user, pk)
    return render(request, "hr/vacancy_detail.html", {
        "vacancy": vacancy,
        "applications": vacancy.applications.all(),
        "can_add": vacancy.status == VacancyStatus.OPEN,
    })


@recruitment_editor_required
def vacancy_edit(request, pk):
    vacancy = get_vacancy(request.user, pk)
    if vacancy.status == VacancyStatus.CLOSED:
        messages.error(request, "A closed vacancy cannot be reopened.")
        return redirect("hr:vacancy_detail", pk=vacancy.pk)
    form = VacancyForm(request.POST or None, instance=vacancy, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        remember_owner(saved, request.user, "created_by")
        saved.save()
        messages.success(request, "Vacancy saved.")
        return redirect("hr:vacancy_detail", pk=saved.pk)
    return render(request, "hr/vacancy_form.html", {
        "form": form,
        "vacancy": vacancy,
        "heading": "Update vacancy",
        "submit_label": "Save vacancy",
    })


@recruitment_editor_required
def application_create(request, pk):
    vacancy = get_vacancy(request.user, pk)
    if vacancy.status != VacancyStatus.OPEN:
        messages.error(request, "Add an application only while the vacancy is open.")
        return redirect("hr:vacancy_detail", pk=vacancy.pk)
    form = ApplicationForm(request.POST or None, vacancy=vacancy)
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        remember_owner(application, request.user, "filed_by")
        try:
            application.save()
        except IntegrityError:
            form.add_error(None, "This person has already applied for this vacancy.")
        else:
            messages.success(request, "Application saved.")
            return redirect("hr:application_detail", pk=application.pk)
    return render(request, "hr/application_form.html", {
        "form": form,
        "vacancy": vacancy,
        "heading": "Add application",
        "submit_label": "Save application",
    })


@hr_login_required
def application_detail(request, pk):
    application = get_application(request.user, pk)
    return render(request, "hr/application_detail.html", {
        "application": application,
        "can_hire": (
            application.status == ApplicationStatus.OFFERED
            and application.vacancy.status == VacancyStatus.OPEN
            and not application.employee_id
        ),
    })


@recruitment_editor_required
def application_edit(request, pk):
    application = get_application(request.user, pk)
    if application.status == ApplicationStatus.HIRED:
        messages.error(request, "A hired application cannot be changed.")
        return redirect("hr:application_detail", pk=application.pk)
    form = ApplicationForm(request.POST or None, instance=application, vacancy=application.vacancy)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        remember_owner(saved, request.user, "filed_by")
        try:
            saved.save()
        except IntegrityError:
            form.add_error(None, "This person has already applied for this vacancy.")
        else:
            messages.success(request, "Application saved.")
            return redirect("hr:application_detail", pk=saved.pk)
    return render(request, "hr/application_form.html", {
        "form": form,
        "application": application,
        "vacancy": application.vacancy,
        "heading": "Update application",
        "submit_label": "Save application",
    })


@recruitment_editor_required
def application_hire(request, pk):
    application = get_application(request.user, pk)
    if application.status == ApplicationStatus.HIRED and application.employee_id:
        return redirect("hr:employee_detail", pk=application.employee_id)
    if application.status != ApplicationStatus.OFFERED or application.vacancy.status != VacancyStatus.OPEN:
        messages.error(request, "Offer the job before you hire this person.")
        return redirect("hr:application_detail", pk=application.pk)
    form = HireForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            employee = application.hire(request.user, **form.cleaned_data)
        except ValidationError as exc:
            if getattr(exc, "error_dict", None):
                for errors in exc.error_dict.values():
                    for error in errors:
                        form.add_error(None, error)
            else:
                form.add_error(None, exc)
        else:
            messages.success(request, "Employee saved.")
            return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/hire_form.html", {
        "form": form,
        "application": application,
        "heading": "Hire applicant",
        "submit_label": "Create employee",
    })
