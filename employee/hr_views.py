import os
from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from employee.access import can_edit_hr, can_run_payroll, can_use_hr, visible_companies, visible_employees
from leave.balance import annual_cycle, balances_for
from performance.records import file_summary
from recruitment.models import Vacancy, VacancyStatus
from recruitment.records import hired_from
from leave.models import LeaveApplication, LeaveStatus
from employee.forms import (
    ContractForm,
    EmployeeDocumentForm,
    DaysPerWeekForm,
    EmployeeForm,
    EmploymentHistoryForm,
    GrossSalaryForm,
    QualificationForm,
)
from employee.models import (
    Department,
    EmployeeDocument,
    EmployeeType,
    Payroll,
    Status,
)


def hr_login_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not can_use_hr(request.user):
            return render(request, "hr/no_access.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def hr_editor_required(view):
    @hr_login_required
    def wrapped(request, *args, **kwargs):
        if not can_edit_hr(request.user):
            return render(request, "hr/read_only.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def employee_queryset(user):
    return visible_employees(user).select_related(
        "designation__department",
        "company",
        "created_by",
    )


def get_employee(user, pk):
    return get_object_or_404(
        employee_queryset(user).prefetch_related(
            "contracts",
            "qualifications",
            "employment_history",
            "documents",
            "bankinfo_set",
        ),
        pk=pk,
    )


@login_required
def after_login(request):
    if can_use_hr(request.user):
        return redirect("hr:home")
    return redirect("hr:no_access")


@login_required
def no_access(request):
    if can_use_hr(request.user):
        return redirect("hr:home")
    return render(request, "hr/no_access.html", status=403)


@hr_login_required
def home(request):
    today = timezone.localdate()
    employees = visible_employees(request.user)
    active_employees = employees.filter(status=Status.ACTIVE).count()
    payroll_runs = Payroll.objects.filter(
        employee__in=employees,
        start_date__year=today.year,
        start_date__month=today.month,
    ).count()
    open_leave = LeaveApplication.objects.filter(
        employee__in=employees,
        status=LeaveStatus.SUBMITTED,
    ).count()
    open_vacancies = Vacancy.objects.filter(
        company__in=visible_companies(request.user),
        status=VacancyStatus.OPEN,
    ).count()
    return render(request, "hr/home.html", {
        "active_employees": active_employees,
        "payroll_runs": payroll_runs,
        "open_leave": open_leave,
        "open_vacancies": open_vacancies,
        "month_label": date(today.year, today.month, 1).strftime("%B %Y"),
    })


@hr_login_required
def employee_list(request):
    employees = employee_queryset(request.user)
    total = employees.count()
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "").strip()
    status = request.GET.get("status", "").strip()
    employee_type = request.GET.get("employee_type", "").strip()
    if query:
        employees = employees.filter(
            Q(first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(maiden_name__icontains=query)
            | Q(emp_code__icontains=query)
        )
    if department.isdigit():
        employees = employees.filter(designation__department_id=int(department))
    if status in Status.values:
        employees = employees.filter(status=status)
    if employee_type in EmployeeType.values:
        employees = employees.filter(employee_type=employee_type)
    return render(request, "hr/employee_list.html", {
        "employees": employees.order_by("last_name", "first_name"),
        "total": total,
        "query": query,
        "department": department,
        "status": status,
        "employee_type": employee_type,
        "departments": Department.objects.order_by("name"),
        "statuses": Status.choices,
        "employee_types": EmployeeType.choices,
        "filtered": bool(query or department or status or employee_type),
    })


@hr_editor_required
def employee_create(request):
    form = EmployeeForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.created_by = request.user
        employee.save()
        messages.success(request, "Employee saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/employee_form.html", {
        "form": form,
        "heading": "Add employee",
        "submit_label": "Save employee",
    })


@hr_login_required
def employee_detail(request, pk):
    employee = get_employee(request.user, pk)
    gross_form = GrossSalaryForm(instance=employee)
    days_form = DaysPerWeekForm(instance=employee)
    if request.method == "POST":
        if not (can_edit_hr(request.user) or can_run_payroll(request.user)):
            return render(request, "hr/read_only.html", status=403)
        action = request.POST.get("employee_action")
        if action == "save_pay":
            gross_form = GrossSalaryForm(request.POST, instance=employee)
            if gross_form.is_valid():
                gross_form.save()
                messages.success(request, "Gross salary saved.")
                return redirect("hr:employee_detail", pk=employee.pk)
        elif action == "save_days_per_week" and can_edit_hr(request.user):
            days_form = DaysPerWeekForm(request.POST, instance=employee)
            if days_form.is_valid():
                days_form.save()
                messages.success(request, "Days per week saved.")
                return redirect("hr:employee_detail", pk=employee.pk)
    leave_as_of = timezone.localdate()
    return render(request, "hr/employee_detail.html", {
        "employee": employee,
        "gross_form": gross_form,
        "days_form": days_form,
        "current_contract": employee.contracts.filter(is_current=True).first(),
        "contracts": employee.contracts.all(),
        "qualifications": employee.qualifications.all(),
        "history": employee.employment_history.all(),
        "documents": employee.documents.all(),
        "banks": employee.bankinfo_set.all(),
        "leave_as_of": leave_as_of,
        "leave_cycle": annual_cycle(employee, leave_as_of),
        "leave_balances": balances_for(employee, leave_as_of),
        "leave_applications": employee.leave_applications.select_related("leave_type"),
        **file_summary(employee),
        "recruitment_application": hired_from(employee),
    })


@hr_editor_required
def employee_edit(request, pk):
    employee = get_employee(request.user, pk)
    form = EmployeeForm(request.POST or None, instance=employee, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Employee saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/employee_form.html", {
        "form": form,
        "employee": employee,
        "heading": "Edit employee",
        "submit_label": "Save employee",
    })


@hr_editor_required
def contract_form(request, pk):
    employee = get_employee(request.user, pk)
    replace = request.GET.get("new") == "1" or request.POST.get("replace") == "1"
    current = None if replace else employee.contracts.filter(is_current=True).first()
    has_current = employee.contracts.filter(is_current=True).exists()
    form = ContractForm(request.POST or None, instance=current)
    if request.method == "POST" and form.is_valid():
        contract = form.save(commit=False)
        contract.employee = employee
        contract.is_current = True
        contract.save()
        messages.success(request, "Contract saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/contract_form.html", {
        "form": form,
        "employee": employee,
        "replace": replace,
        "has_current": has_current,
        "submit_label": "Save contract",
    })


@hr_editor_required
def qualification_create(request, pk):
    employee = get_employee(request.user, pk)
    form = QualificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        qualification = form.save(commit=False)
        qualification.employee = employee
        qualification.save()
        messages.success(request, "Qualification saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/qualification_form.html", {
        "form": form,
        "employee": employee,
        "heading": "Add qualification",
        "submit_label": "Save qualification",
    })


@hr_editor_required
def qualification_edit(request, pk, qualification_pk):
    employee = get_employee(request.user, pk)
    qualification = get_object_or_404(employee.qualifications.all(), pk=qualification_pk)
    form = QualificationForm(request.POST or None, instance=qualification)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Qualification saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/qualification_form.html", {
        "form": form,
        "employee": employee,
        "heading": "Edit qualification",
        "submit_label": "Save qualification",
    })


@hr_editor_required
def history_create(request, pk):
    employee = get_employee(request.user, pk)
    form = EmploymentHistoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        row = form.save(commit=False)
        row.employee = employee
        row.save()
        messages.success(request, "Employment history saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/history_form.html", {
        "form": form,
        "employee": employee,
        "heading": "Add employment history",
        "submit_label": "Save employment history",
    })


@hr_editor_required
def history_edit(request, pk, history_pk):
    employee = get_employee(request.user, pk)
    row = get_object_or_404(employee.employment_history.all(), pk=history_pk)
    form = EmploymentHistoryForm(request.POST or None, instance=row)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Employment history saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/history_form.html", {
        "form": form,
        "employee": employee,
        "heading": "Edit employment history",
        "submit_label": "Save employment history",
    })


@hr_editor_required
def document_create(request, pk):
    employee = get_employee(request.user, pk)
    form = EmployeeDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.employee = employee
        document.uploaded_by = request.user
        document.save()
        messages.success(request, "Document saved.")
        return redirect("hr:employee_detail", pk=employee.pk)
    return render(request, "hr/document_form.html", {
        "form": form,
        "employee": employee,
        "submit_label": "Upload document",
    })


@hr_login_required
def document_download(request, pk):
    document = get_object_or_404(
        EmployeeDocument.objects.select_related("employee"),
        pk=pk,
        employee__in=visible_employees(request.user),
    )
    try:
        handle = document.file.open("rb")
    except FileNotFoundError:
        raise Http404("Document file is missing.")
    filename = os.path.basename(document.file.name)
    return FileResponse(handle, as_attachment=True, filename=filename)
