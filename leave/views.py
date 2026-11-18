import os
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from employee.access import can_edit_hr, can_manage_leave, visible_employees
from employee.hr_views import employee_queryset, hr_editor_required, hr_login_required
from leave.balance import absenteeism_counts, balances_for, monday_of
from leave.forms import AttendanceFormSet, LeaveApplicationForm
from leave.models import Attendance, LeaveApplication, LeaveStatus


def manager_required(view):
    @hr_login_required
    def wrapped(request, *args, **kwargs):
        if not can_manage_leave(request.user):
            return render(request, "hr/manager_only.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def visible_applications(user):
    return LeaveApplication.objects.filter(
        employee__in=visible_employees(user),
    ).select_related("employee", "leave_type", "captured_by", "decided_by")


def get_application(user, pk):
    return get_object_or_404(visible_applications(user), pk=pk)


def attach_validation(form, exc):
    if getattr(exc, "message_dict", None):
        for field, field_messages in exc.message_dict.items():
            target = field if field in form.fields else None
            for message in field_messages:
                form.add_error(target, message)
    else:
        form.add_error(None, exc)


def save_application(form, user, status):
    application = form.save(commit=False)
    application.status = status
    application.captured_by = user
    try:
        application.full_clean()
    except ValidationError as exc:
        attach_validation(form, exc)
        return None
    application.save()
    return application


def initial_employee(request):
    raw = request.GET.get("employee", "")
    if not raw.isdigit():
        return {}
    if visible_employees(request.user).filter(pk=int(raw)).exists():
        return {"employee": int(raw)}
    return {}


@hr_login_required
def leave_list(request):
    applications = visible_applications(request.user)
    return render(request, "hr/leave_list.html", {
        "applications": applications,
    })


@hr_editor_required
def leave_create(request):
    if request.method == "POST":
        form = LeaveApplicationForm(request.POST, request.FILES, user=request.user)
        status = LeaveStatus.DRAFT if request.POST.get("action") == "draft" else LeaveStatus.SUBMITTED
        if form.is_valid():
            application = save_application(form, request.user, status)
            if application is not None:
                if status == LeaveStatus.SUBMITTED:
                    messages.success(request, "Leave submitted.")
                else:
                    messages.success(request, "Draft saved.")
                return redirect("hr:leave_detail", pk=application.pk)
    else:
        form = LeaveApplicationForm(user=request.user, initial=initial_employee(request))
    return render(request, "hr/leave_form.html", {
        "form": form,
        "heading": "Capture leave",
        "submit_label": "Submit leave",
    })


@hr_login_required
def leave_detail(request, pk):
    application = get_application(request.user, pk)
    balance = next(
        (
            row for row in balances_for(application.employee, application.start_date)
            if row["leave_type"].pk == application.leave_type_id
        ),
        None,
    )
    return render(request, "hr/leave_detail.html", {
        "application": application,
        "balance": balance,
    })


@hr_login_required
def leave_proof(request, pk):
    application = get_application(request.user, pk)
    if not application.proof:
        raise Http404("No proof is attached.")
    try:
        handle = application.proof.open("rb")
    except FileNotFoundError:
        raise Http404("Proof file is missing.")
    filename = os.path.basename(application.proof.name)
    return FileResponse(handle, as_attachment=True, filename=filename)


@hr_editor_required
def leave_edit(request, pk):
    application = get_application(request.user, pk)
    if application.status != LeaveStatus.DRAFT:
        messages.error(request, "Only a draft can be edited.")
        return redirect("hr:leave_detail", pk=application.pk)
    if request.method == "POST":
        form = LeaveApplicationForm(request.POST, request.FILES, instance=application, user=request.user)
        status = LeaveStatus.DRAFT if request.POST.get("action") == "draft" else LeaveStatus.SUBMITTED
        if form.is_valid():
            saved = save_application(form, request.user, status)
            if saved is not None:
                if status == LeaveStatus.SUBMITTED:
                    messages.success(request, "Leave submitted.")
                else:
                    messages.success(request, "Draft saved.")
                return redirect("hr:leave_detail", pk=saved.pk)
    else:
        form = LeaveApplicationForm(instance=application, user=request.user)
    return render(request, "hr/leave_form.html", {
        "form": form,
        "application": application,
        "heading": "Edit draft",
        "submit_label": "Submit leave",
    })


@hr_editor_required
def leave_cancel(request, pk):
    application = get_application(request.user, pk)
    if request.method != "POST":
        return redirect("hr:leave_detail", pk=application.pk)
    if not application.can_cancel:
        messages.error(request, "This application cannot be cancelled.")
        return redirect("hr:leave_detail", pk=application.pk)
    application.status = LeaveStatus.CANCELLED
    application.save()
    messages.success(request, "Leave cancelled.")
    return redirect("hr:leave_detail", pk=application.pk)


@manager_required
def leave_approvals(request):
    applications = visible_applications(request.user).filter(status=LeaveStatus.SUBMITTED)
    return render(request, "hr/leave_approvals.html", {
        "applications": applications,
    })


@manager_required
def leave_decide(request, pk):
    application = get_application(request.user, pk)
    balance = next(
        (
            row for row in balances_for(application.employee, application.start_date)
            if row["leave_type"].pk == application.leave_type_id
        ),
        None,
    )
    error = ""
    note = ""
    if request.method == "POST":
        if application.status != LeaveStatus.SUBMITTED:
            messages.error(request, "This application is no longer waiting for a decision.")
            return redirect("hr:leave_detail", pk=application.pk)
        linked_user_id = _linked_user_id(application.employee)
        note = (request.POST.get("decision_note") or "").strip()
        action = request.POST.get("action")
        if linked_user_id and linked_user_id == request.user.pk:
            error = "You cannot approve your own leave."
        elif action == "decline" and not note:
            error = "Enter a note to decline this leave."
        elif action == "approve":
            application.status = LeaveStatus.APPROVED
            application.decision_note = note
            application.decided_by = request.user
            application.decided_at = timezone.now()
            try:
                application.full_clean()
            except ValidationError as exc:
                application.refresh_from_db()
                error = _first_message(exc)
            else:
                application.save()
                messages.success(request, "Leave approved.")
                return redirect("hr:leave_detail", pk=application.pk)
        elif action == "decline":
            application.status = LeaveStatus.DECLINED
            application.decision_note = note
            application.decided_by = request.user
            application.decided_at = timezone.now()
            application.save()
            messages.success(request, "Leave declined.")
            return redirect("hr:leave_detail", pk=application.pk)
        else:
            error = "Choose approve or decline."
    return render(request, "hr/leave_decide.html", {
        "application": application,
        "balance": balance,
        "error": error,
        "note": note,
    })


def _linked_user_id(employee):
    """Phase 6 adds the employee sign-in. Until that field exists, nobody is blocked here."""
    names = {field.attname for field in employee._meta.concrete_fields}
    if "user_id" not in names:
        return None
    return employee.user_id


def _first_message(exc):
    if getattr(exc, "message_dict", None):
        for field_messages in exc.message_dict.values():
            if field_messages:
                return field_messages[0]
    if exc.messages:
        return exc.messages[0]
    return "This leave could not be saved."


def parse_iso_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def attendance_rows(user, day):
    employees = list(employee_queryset(user).order_by("last_name", "first_name"))
    existing = {
        row.employee_id: row
        for row in Attendance.objects.filter(employee__in=employees, date=day)
    }
    return employees, existing


@hr_login_required
def attendance_register(request):
    if request.method == "POST" and not can_edit_hr(request.user):
        return render(request, "hr/read_only.html", status=403)
    raw = request.POST.get("date") if request.method == "POST" else request.GET.get("date")
    date_error = ""
    if raw:
        day = parse_iso_date(raw)
        if day is None:
            day = timezone.localdate()
            date_error = "Enter a valid date."
    else:
        day = timezone.localdate()
    employees, existing = attendance_rows(request.user, day)
    allowed_ids = {employee.pk for employee in employees}
    initial = [
        {
            "employee_id": employee.pk,
            "status": existing[employee.pk].status if employee.pk in existing else "",
            "hours_worked": existing[employee.pk].hours_worked if employee.pk in existing else "",
        }
        for employee in employees
    ]
    formset = None
    if can_edit_hr(request.user) and employees and not date_error:
        formset = AttendanceFormSet(
            request.POST or None,
            initial=None if request.method == "POST" else initial,
            form_kwargs={"allowed_ids": allowed_ids},
        )
        if request.method == "POST" and formset.is_valid():
            with transaction.atomic():
                for form in formset:
                    data = form.cleaned_data
                    Attendance.objects.update_or_create(
                        employee_id=data["employee_id"],
                        date=day,
                        defaults={
                            "status": data["status"],
                            "hours_worked": data["hours_worked"],
                            "recorded_by": request.user,
                        },
                    )
            messages.success(request, "Attendance saved.")
            return redirect(f"{request.path}?date={day.isoformat()}")
    view_rows = [
        {"employee": employee, "record": existing.get(employee.pk)}
        for employee in employees
    ]
    paired = []
    if formset is not None:
        by_id = {employee.pk: employee for employee in employees}
        for form in formset:
            raw_id = form["employee_id"].value()
            try:
                employee = by_id.get(int(raw_id))
            except (TypeError, ValueError):
                employee = None
            paired.append({"employee": employee, "form": form})
    return render(request, "hr/attendance.html", {
        "day": day,
        "date_error": date_error,
        "employees": employees,
        "view_rows": view_rows,
        "paired": paired,
        "formset": formset,
    })


@hr_login_required
def timesheet(request):
    raw = request.GET.get("week")
    anchor = parse_iso_date(raw) if raw else timezone.localdate()
    week_error = ""
    if raw and anchor is None:
        anchor = timezone.localdate()
        week_error = "Enter a valid date."
    if anchor is None:
        anchor = timezone.localdate()
    start = monday_of(anchor)
    days = [start + timedelta(days=offset) for offset in range(7)]
    end = days[-1]
    employees = list(employee_queryset(request.user).order_by("last_name", "first_name"))
    recorded = list(
        Attendance.objects.filter(employee__in=employees, date__range=(start, end))
    )
    by_employee = {}
    for row in recorded:
        by_employee.setdefault(row.employee_id, {})[row.date] = row
    absent = absenteeism_counts(employees, start, end, recorded)
    rows = []
    for employee in employees:
        daily = by_employee.get(employee.pk, {})
        hours = []
        total = Decimal("0.00")
        for day in days:
            record = daily.get(day)
            if record is None:
                hours.append(None)
            else:
                hours.append(record.hours_worked)
                total += record.hours_worked
        rows.append({
            "employee": employee,
            "hours": hours,
            "total": total if daily else None,
            "absenteeism": absent.get(employee.pk, 0),
        })
    return render(request, "hr/timesheet.html", {
        "start": start,
        "end": end,
        "days": days,
        "rows": rows,
        "has_attendance": bool(recorded),
        "week_value": start.isoformat(),
        "week_error": week_error,
    })
