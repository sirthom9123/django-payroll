from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from leave.holidays import is_public_holiday
from leave.models import AnnualAccrual, Attendance, AttendanceStatus, LeaveApplication, LeaveKind, LeaveStatus


def days(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def working_days(start, end):
    """Monday to Friday, inclusive. Public holidays stay in this count."""
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return days(count)


def _works_a_five_day_week(employee):
    per_week = getattr(employee, "days_per_week", None)
    return per_week is None or per_week >= 5


def annual_leave_days(start, end, employee):
    """Working days charged to annual leave.

    BCEA section 20(8): a public holiday that falls on a day the employee
    would ordinarily have worked is an extra paid day, so it is not deducted.
    A five-day week is assumed until days per week is below 5. Below that,
    the weekday they skip is not known, so the holiday stays in the count.
    """
    count = 0
    day = start
    skip_holidays = _works_a_five_day_week(employee)
    while day <= end:
        if day.weekday() < 5 and not (skip_holidays and is_public_holiday(day)):
            count += 1
        day += timedelta(days=1)
    return days(count)


def add_months(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        last = 29 if leap else 28
    elif month in (4, 6, 9, 11):
        last = 30
    else:
        last = 31
    return date(year, month, min(day.day, last))


def cycle_bounds(hired, on_date, length_months):
    """The employment cycle of `length_months` that contains on_date."""
    if hired is None or on_date < hired:
        return None
    start = hired
    while True:
        nxt = add_months(start, length_months)
        if on_date < nxt:
            return start, nxt - timedelta(days=1)
        start = nxt


def annual_cycle(employee, on_date):
    return cycle_bounds(employee.date_hired, on_date, 12)


def portion(cap, start, end, on_date):
    """Share of cap accumulated from the cycle start up to on_date."""
    if cap <= 0 or on_date < start:
        return Decimal("0.00")
    if on_date > end:
        on_date = end
    length = (end - start).days + 1
    elapsed = (on_date - start).days + 1
    return days(cap * Decimal(elapsed) / Decimal(length))


def dates_overlap(application):
    qs = LeaveApplication.objects.filter(
        employee_id=application.employee_id,
        status__in=(LeaveStatus.SUBMITTED, LeaveStatus.APPROVED),
        start_date__lte=application.end_date,
        end_date__gte=application.start_date,
    )
    if application.pk:
        qs = qs.exclude(pk=application.pk)
    return qs.exists()


def usage_between(employee, leave_type, start, end, exclude_pk=None):
    if start is None or end is None:
        return Decimal("0.00"), Decimal("0.00")
    qs = LeaveApplication.objects.filter(
        employee=employee,
        leave_type=leave_type,
        start_date__gte=start,
        start_date__lte=end,
        status__in=(LeaveStatus.SUBMITTED, LeaveStatus.APPROVED),
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    taken = Decimal("0.00")
    pending = Decimal("0.00")
    for amount, status in qs.values_list("days", "status"):
        if status == LeaveStatus.APPROVED:
            taken += amount
        else:
            pending += amount
    return taken, pending


def maternity_last_day(start):
    """Four consecutive months."""
    return add_months(start, 4) - timedelta(days=1)


def parental_last_day(start, shared):
    """Van Wyk interim reading-in of BCEA section 25, from 3 October 2025.

    The only employed parent gets four consecutive months. Where both parents
    are employed, this employee's share cannot pass four months and ten days.
    The other parent's days are not visible here.
    """
    if shared:
        return add_months(start, 4) + timedelta(days=9)
    return maternity_last_day(start)


def _spans_touch(left, right):
    return left[0] <= right[1] + timedelta(days=1) and right[0] <= left[1] + timedelta(days=1)


def _parental_rows(application):
    qs = LeaveApplication.objects.filter(
        employee_id=application.employee_id,
        leave_type__kind=LeaveKind.PARENTAL,
        status__in=(LeaveStatus.SUBMITTED, LeaveStatus.APPROVED),
    )
    if application.pk:
        qs = qs.exclude(pk=application.pk)
    return list(qs.values_list("start_date", "end_date", "other_parent_employed"))


def parental_refusal(application):
    """None when this parental application fits one uninterrupted run."""
    start = application.start_date
    end = application.end_date
    shared = bool(application.other_parent_employed)
    others = _parental_rows(application)
    for other_start, other_end, other_shared in others:
        other_flag = shared if other_shared is None else bool(other_shared)
        window_end = parental_last_day(other_start, other_flag)
        same_event = other_start <= start <= window_end or start <= other_start <= parental_last_day(start, shared)
        if same_event and not _spans_touch((start, end), (other_start, other_end)):
            return "Parental leave must be taken in one uninterrupted run of days."
    cluster = [(start, end, shared)]
    pending = [(item[0], item[1], shared if item[2] is None else bool(item[2])) for item in others]
    changed = True
    while changed:
        changed = False
        remaining = []
        for span in pending:
            if any(_spans_touch(span, item) for item in cluster):
                cluster.append(span)
                changed = True
            else:
                remaining.append(span)
        pending = remaining
    block_start = min(item[0] for item in cluster)
    block_end = max(item[1] for item in cluster)
    block_shared = all(item[2] for item in cluster)
    if block_end > parental_last_day(block_start, block_shared):
        if block_shared:
            return "Parental leave cannot be longer than 4 months and 10 days."
        return "Parental leave for the only employed parent cannot be longer than 4 consecutive months."
    return None


def _paid_and_unpaid_spans(employee, start, end):
    rows = LeaveApplication.objects.filter(
        employee=employee,
        status=LeaveStatus.APPROVED,
        start_date__lte=end,
        end_date__gte=start,
    ).values_list("start_date", "end_date", "leave_type__kind")
    paid = []
    unpaid = []
    for leave_start, leave_end, kind in rows:
        if kind == LeaveKind.UNPAID:
            unpaid.append((leave_start, leave_end))
        else:
            paid.append((leave_start, leave_end))
    return paid, unpaid


def _covered(spans, day):
    return any(leave_start <= day <= leave_end for leave_start, leave_end in spans)


def qualifying_days(employee, start, end):
    """Weekdays worked or entitled to be paid, for the 1-in-17 agreement.

    A recorded absence does not count unless approved paid leave covers it.
    Approved unpaid leave does not count. A public holiday on a weekday counts.
    When days per week is below 5, the count is scaled by that fraction of a
    five-day week, because the register does not say which weekdays are off.
    """
    if start is None or end is None or end < start:
        return Decimal("0.00")
    absent = set(
        Attendance.objects.filter(
            employee=employee,
            date__gte=start,
            date__lte=end,
            status=AttendanceStatus.ABSENT,
        ).values_list("date", flat=True)
    )
    paid, unpaid = _paid_and_unpaid_spans(employee, start, end)
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5 and not _covered(unpaid, day):
            if day not in absent or _covered(paid, day):
                count += 1
        day += timedelta(days=1)
    per_week = employee.days_per_week
    if per_week is not None and per_week < 5:
        return days(Decimal(count) * Decimal(per_week) / Decimal(5))
    return days(count)


def entitlement(employee, leave_type, on_date, exclude_pk=None):
    """Days accumulated by on_date, before this cycle's taken and pending rows.

    Annual leave also keeps unused days from the previous cycle for six months
    (BCEA section 20(4)).
    """
    hired = employee.date_hired
    kind = leave_type.kind
    cap = leave_type.days_per_year
    if kind in (LeaveKind.UNPAID, LeaveKind.MATERNITY, LeaveKind.PARENTAL):
        return Decimal("0.00"), annual_cycle(employee, on_date) if hired else None
    if not hired or on_date < hired:
        return Decimal("0.00"), None

    if kind == LeaveKind.SICK:
        cycle = cycle_bounds(hired, on_date, 36)
        if cycle is None:
            return Decimal("0.00"), None
        if on_date < add_months(hired, 6):
            accrued = days(working_days(hired, on_date) / Decimal(26))
            return min(accrued, cap), cycle
        return cap, cycle

    cycle = annual_cycle(employee, on_date)
    if cycle is None:
        return Decimal("0.00"), None
    start, end = cycle
    if kind == LeaveKind.FAMILY:
        if employee.days_per_week is None or employee.days_per_week < 4:
            return Decimal("0.00"), cycle
        if on_date <= add_months(hired, 4):
            return Decimal("0.00"), cycle
        return cap, cycle

    if kind == LeaveKind.ANNUAL and leave_type.accrual == AnnualAccrual.PER_17:
        accrued = days(qualifying_days(employee, start, on_date) / Decimal(17))
    else:
        accrued = portion(cap, start, end, on_date)
    if kind != LeaveKind.ANNUAL or start <= hired:
        return accrued, cycle
    previous_end = start - timedelta(days=1)
    previous = cycle_bounds(hired, previous_end, 12)
    if previous is None or on_date > add_months(previous[1], 6):
        return accrued, cycle
    earned = (
        days(qualifying_days(employee, previous[0], previous[1]) / Decimal(17))
        if leave_type.accrual == AnnualAccrual.PER_17
        else portion(cap, previous[0], previous[1], previous[1])
    )
    taken, pending = usage_between(
        employee, leave_type, previous[0], previous[1], exclude_pk=exclude_pk,
    )
    carry = earned - taken - pending
    if carry < 0:
        carry = Decimal("0.00")
    return accrued + carry, cycle


def has_enough(application):
    if application.leave_type.kind == LeaveKind.UNPAID:
        return True
    if application.leave_type.kind == LeaveKind.MATERNITY:
        return application.end_date <= maternity_last_day(application.start_date)
    if application.leave_type.kind == LeaveKind.PARENTAL:
        if application.other_parent_employed is None:
            return False
        return parental_refusal(application) is None
    pool, cycle = entitlement(
        application.employee,
        application.leave_type,
        application.start_date,
        exclude_pk=application.pk,
    )
    if cycle is None:
        return False
    taken, pending = usage_between(
        application.employee,
        application.leave_type,
        cycle[0],
        cycle[1],
        exclude_pk=application.pk,
    )
    if application.status == LeaveStatus.APPROVED:
        available = pool - taken
    else:
        available = pool - taken - pending
    return available >= application.days


def leave_refusal_message(application):
    employee = application.employee
    kind = application.leave_type.kind
    if not employee.date_hired:
        return "Enter a hire date before capturing leave."
    if kind == LeaveKind.FAMILY:
        if employee.days_per_week is None:
            return "Enter how many days a week this employee works before capturing family responsibility leave."
        if employee.days_per_week < 4:
            return "Family responsibility leave is for an employee who works at least 4 days a week."
        if employee.date_hired and application.start_date <= add_months(employee.date_hired, 4):
            return "Family responsibility leave is available after 4 months of employment."
    return "You do not have enough leave for these dates."


def validate_application(application):
    errors = {}
    start = application.start_date
    end = application.end_date
    kind = application.leave_type.kind if application.leave_type_id else None
    if start and end:
        if end < start:
            errors["end_date"] = "End date must be on or after the start date."
        else:
            if kind == LeaveKind.ANNUAL and application.employee_id:
                application.days = annual_leave_days(start, end, application.employee)
            else:
                application.days = working_days(start, end)
            if application.days <= 0:
                holiday = kind == LeaveKind.ANNUAL and any(
                    is_public_holiday(start + timedelta(days=offset))
                    for offset in range((end - start).days + 1)
                )
                if holiday:
                    errors["end_date"] = "This public holiday is not deducted from annual leave."
                else:
                    errors["end_date"] = "These dates do not include a working day."
    if application.employee_id and not application.employee.company_id:
        errors["employee"] = "This employee has no company, so leave cannot be captured."
    elif (
        application.employee_id
        and application.leave_type_id
        and application.employee.company_id != application.leave_type.company_id
    ):
        errors["leave_type"] = "Choose a leave type for this employee's company."
    needs_hire = kind not in (LeaveKind.UNPAID, LeaveKind.MATERNITY, LeaveKind.PARENTAL, None)
    reserving = application.status in (LeaveStatus.SUBMITTED, LeaveStatus.APPROVED)
    if (
        not errors
        and reserving
        and needs_hire
        and application.employee_id
        and not application.employee.date_hired
    ):
        errors["employee"] = "Enter a hire date before capturing leave."
    if (
        not errors
        and reserving
        and start
        and end
        and application.leave_type_id
        and application.employee_id
    ):
        if dates_overlap(application):
            errors["start_date"] = "These dates overlap leave already on your record."
        elif kind == LeaveKind.MATERNITY and end > maternity_last_day(start):
            errors["end_date"] = "Maternity leave cannot be longer than 4 consecutive months."
        elif kind == LeaveKind.PARENTAL and application.other_parent_employed is None:
            errors["other_parent_employed"] = "Say whether the other parent is also employed."
        elif kind == LeaveKind.PARENTAL and parental_refusal(application):
            errors["end_date"] = parental_refusal(application)
        elif not has_enough(application):
            errors["start_date"] = leave_refusal_message(application)
    if errors:
        raise ValidationError(errors)


def _labels(kind, entitled, remaining):
    if kind == LeaveKind.UNPAID:
        return "—", "Not limited"
    if kind == LeaveKind.MATERNITY:
        return "4 months", "4 consecutive months"
    if kind == LeaveKind.PARENTAL:
        return "4 months", "4 months, or 4 months and 10 days"
    return f"{entitled:.2f}", f"{remaining:.2f}"


def _detail(leave_type):
    kind = leave_type.kind
    if kind == LeaveKind.ANNUAL:
        if leave_type.accrual == AnnualAccrual.PER_17:
            return "By agreement, 1 day for every 17 weekdays worked or paid. A recorded absence that is not paid leave does not count. Unused days from the previous cycle stay for 6 months."
        return "Accumulates over the leave cycle from the date hired. A public holiday on a weekday is not deducted. Unused days from the previous cycle stay for 6 months."
    if kind == LeaveKind.SICK:
        return "30 days over 36 months on a five-day week, after the first 6 months. Before that, 1 day for every 26 weekdays worked."
    if kind == LeaveKind.FAMILY:
        return "3 days in each leave cycle, after 4 months, for an employee who works at least 4 days a week."
    if kind == LeaveKind.MATERNITY:
        return "4 consecutive months. It is not a yearly day balance."
    if kind == LeaveKind.PARENTAL:
        return "4 consecutive months when this employee is the only employed parent. When both parents are employed, they share 4 months and 10 days. One uninterrupted run of days."
    if kind == LeaveKind.STUDY:
        return "No statutory number. Days accumulate only after the company sets an allowance."
    return "Not limited."


def _cycle_label(cycle):
    if cycle is None:
        return ""
    start, end = cycle
    return f"{start.day} {start.strftime('%B %Y')} – {end.day} {end.strftime('%B %Y')}"


def balances_for(employee, on_date):
    if not employee.company_id:
        return []
    rows = []
    for leave_type in employee.company.leave_types.all():
        pool, cycle = entitlement(employee, leave_type, on_date)
        if cycle is None:
            taken, pending = Decimal("0.00"), Decimal("0.00")
        else:
            taken, pending = usage_between(employee, leave_type, cycle[0], cycle[1])
        if leave_type.kind == LeaveKind.MATERNITY or leave_type.kind == LeaveKind.PARENTAL:
            remaining = Decimal("0.00")
        else:
            remaining = pool - taken - pending
        entitled_label, remaining_label = _labels(leave_type.kind, pool, remaining)
        rows.append({
            "leave_type": leave_type,
            "entitled": pool,
            "taken": taken,
            "pending": pending,
            "remaining": remaining,
            "limited": leave_type.kind not in (LeaveKind.UNPAID, LeaveKind.MATERNITY, LeaveKind.PARENTAL),
            "entitled_label": entitled_label,
            "remaining_label": remaining_label,
            "detail": _detail(leave_type),
            "cycle_label": _cycle_label(cycle),
        })
    return rows


def absenteeism_counts(employees, start, end, attendance_rows):
    spans = {}
    approved = LeaveApplication.objects.filter(
        employee__in=employees,
        status=LeaveStatus.APPROVED,
        start_date__lte=end,
        end_date__gte=start,
    )
    for employee_id, leave_start, leave_end in approved.values_list("employee_id", "start_date", "end_date"):
        spans.setdefault(employee_id, []).append((leave_start, leave_end))
    counts = {employee.pk: 0 for employee in employees}
    for row in attendance_rows:
        if row.status != AttendanceStatus.ABSENT:
            continue
        covered = spans.get(row.employee_id, [])
        if any(leave_start <= row.date <= leave_end for leave_start, leave_end in covered):
            continue
        counts[row.employee_id] = counts.get(row.employee_id, 0) + 1
    return counts


def monday_of(day):
    return day - timedelta(days=day.weekday())
