from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render

from employee.access import can_run_payroll, can_use_hr, visible_employees
from employee.forms import (
    AllowanceLineFormSet,
    DeductionLineFormSet,
    PayrollPaymentForm,
    PayrollReportForm,
    PayrollRunForm,
    TaxBandInlineFormSet,
    TaxYearForm,
)
from employee.models import Payroll, PayrollPayment, TaxYear
from employee.payroll_math import money
from employee.views import render_payroll_pdf


def payroll_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not can_use_hr(request.user):
            return render(request, "hr/no_access.html", status=403)
        if not can_run_payroll(request.user):
            return render(request, "hr/payroll_denied.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def payroll_queryset(user):
    paid = PayrollPayment.objects.filter(payroll=OuterRef("pk"))
    return (
        Payroll.objects.filter(employee__in=visible_employees(user))
        .select_related("employee", "employee__company", "created_by")
        .prefetch_related("benefits", "deductions", "allowance_lines", "deduction_lines")
        .annotate(is_paid=Exists(paid))
        .order_by("-start_date", "-id")
    )


@payroll_required
def payroll_list(request):
    runs = payroll_queryset(request.user)
    return render(request, "hr/payroll_list.html", {"runs": runs})


@payroll_required
def payroll_create(request):
    payroll = Payroll(created_by=request.user)
    return _payroll_form(
        request,
        payroll,
        heading="New payroll run",
        submit_label="Save payroll run",
    )


@payroll_required
def payroll_edit(request, pk):
    payroll = get_object_or_404(payroll_queryset(request.user), pk=pk)
    if payroll.is_paid:
        messages.error(request, "This payroll run has been paid.")
        return redirect("hr:payroll_detail", pk=payroll.pk)
    return _payroll_form(
        request,
        payroll,
        heading="Edit payroll run",
        submit_label="Save payroll run",
    )


def _payroll_form(request, payroll, heading, submit_label):
    if request.method == "POST":
        form = PayrollRunForm(request.POST, instance=payroll, user=request.user)
        allowances = AllowanceLineFormSet(request.POST, instance=payroll, prefix="allowances")
        deductions = DeductionLineFormSet(request.POST, instance=payroll, prefix="deductions")
        if form.is_valid() and allowances.is_valid() and deductions.is_valid():
            with transaction.atomic():
                saved = form.save(commit=False)
                if not saved.created_by_id:
                    saved.created_by = request.user
                if saved.employee.pay_basis() == "hourly":
                    saved.rate = saved.employee.hourly_rate
                else:
                    saved.rate = None
                    saved.hours = Decimal("0.00")
                saved.save()
                allowances.instance = saved
                deductions.instance = saved
                allowances.save()
                deductions.save()
            messages.success(request, "Payroll run saved.")
            return redirect("hr:payroll_detail", pk=saved.pk)
    else:
        form = PayrollRunForm(instance=payroll, user=request.user)
        allowances = AllowanceLineFormSet(instance=payroll, prefix="allowances")
        deductions = DeductionLineFormSet(instance=payroll, prefix="deductions")
    return render(request, "hr/payroll_form.html", {
        "form": form,
        "allowances": allowances,
        "deductions": deductions,
        "payroll": payroll if payroll.pk else None,
        "heading": heading,
        "submit_label": submit_label,
        "pay_people": form.pay_people,
    })


@payroll_required
def payroll_detail(request, pk):
    payroll = get_object_or_404(payroll_queryset(request.user), pk=pk)
    payment = PayrollPayment.objects.filter(payroll=payroll).first()
    return render(request, "hr/payroll_detail.html", {
        "payroll": payroll,
        "payment": payment,
        "paye": payroll.paye_explanation(),
    })


@payroll_required
def payroll_payslip(request, pk):
    payroll = get_object_or_404(payroll_queryset(request.user), pk=pk)
    return render_payroll_pdf(payroll)


@payroll_required
def payroll_payment(request, pk):
    payroll = get_object_or_404(payroll_queryset(request.user), pk=pk)
    if payroll.is_paid:
        messages.error(request, "This payroll run already has a payment.")
        return redirect("hr:payroll_detail", pk=payroll.pk)
    if request.method == "POST":
        form = PayrollPaymentForm(request.POST, payroll=payroll)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.payroll = payroll
            payment.recorded_by = request.user
            try:
                with transaction.atomic():
                    payment.save()
            except IntegrityError:
                messages.error(request, "This payroll run already has a payment.")
                return redirect("hr:payroll_detail", pk=payroll.pk)
            messages.success(request, "Payment recorded.")
            return redirect("hr:payroll_detail", pk=payroll.pk)
    else:
        form = PayrollPaymentForm(payroll=payroll)
    return render(request, "hr/payment_form.html", {
        "form": form,
        "payroll": payroll,
    })


@payroll_required
def payroll_report(request):
    form = PayrollReportForm(request.GET or None, user=request.user)
    report = None
    if request.GET and form.is_valid():
        report = _report_totals(
            request.user,
            form.cleaned_data["company"],
            form.cleaned_data["start_date"],
            form.cleaned_data["end_date"],
        )
    return render(request, "hr/payroll_report.html", {
        "form": form,
        "report": report,
    })


def _report_totals(user, company, start, end):
    runs = list(payroll_queryset(user).filter(
        employee__company=company,
        start_date__gte=start,
        start_date__lte=end,
    ))
    return {
        "company": company,
        "start": start,
        "end": end,
        "runs": runs,
        "headcount": len({run.employee_id for run in runs}),
        "gross": money(sum((run.get_gross_salary for run in runs), Decimal("0"))),
        "paye": money(sum((Decimal(run.income_tax or 0) for run in runs), Decimal("0"))),
        "uif": money(sum((Decimal(run.uif_contribution or 0) for run in runs), Decimal("0"))),
        "nett": money(sum((run.get_nett_salary for run in runs), Decimal("0"))),
    }


@payroll_required
def tax_year_list(request):
    years = TaxYear.objects.prefetch_related("bands")
    return render(request, "hr/tax_year_list.html", {"years": years})


@payroll_required
def tax_year_create(request):
    return _tax_year_form(request, TaxYear(), "New PAYE table", "Save PAYE table")


@payroll_required
def tax_year_edit(request, pk):
    year = get_object_or_404(TaxYear.objects.prefetch_related("bands"), pk=pk)
    return _tax_year_form(request, year, f"PAYE table {year.name}", "Save PAYE table")


def _tax_year_form(request, year, heading, submit_label):
    if request.method == "POST":
        form = TaxYearForm(request.POST, instance=year)
        bands = TaxBandInlineFormSet(request.POST, instance=year, prefix="bands")
        if form.is_valid() and bands.is_valid():
            with transaction.atomic():
                saved = form.save()
                bands.instance = saved
                bands.save()
                updated, paid = saved.refresh_unpaid_runs()
            messages.success(request, "PAYE table saved.")
            if updated:
                messages.success(
                    request,
                    f"{updated} unpaid payroll run(s) in this tax year were recalculated.",
                )
            if paid:
                messages.info(
                    request,
                    f"{paid} paid payroll run(s) were left as filed.",
                )
            return redirect("hr:tax_year_list")
    else:
        form = TaxYearForm(instance=year)
        bands = TaxBandInlineFormSet(instance=year, prefix="bands")
    return render(request, "hr/tax_year_form.html", {
        "form": form,
        "bands": bands,
        "year": year if year.pk else None,
        "heading": heading,
        "submit_label": submit_label,
    })
