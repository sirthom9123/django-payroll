from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from employee.access import can_file_performance, visible_employees
from employee.hr_views import hr_login_required
from performance.forms import (
    AgreementForm,
    AppraisalForm,
    DevelopmentPlanForm,
    ImprovementPlanForm,
    KeyPerformanceAreaForm,
    KeyPerformanceIndicatorForm,
    SkillAssessmentForm,
)
from performance.models import (
    Agreement,
    AgreementStatus,
    Appraisal,
    AppraisalScore,
    DevelopmentPlan,
    ImprovementPlan,
    KeyPerformanceArea,
    KeyPerformanceIndicator,
    SkillAssessment,
)


def performance_editor_required(view):
    @hr_login_required
    def wrapped(request, *args, **kwargs):
        if not can_file_performance(request.user):
            return render(request, "hr/performance_denied.html", status=403)
        return view(request, *args, **kwargs)

    return wrapped


def visible_agreements(user):
    return Agreement.objects.filter(employee__in=visible_employees(user)).select_related(
        "employee",
        "appraisal",
        "filed_by",
    )


def get_agreement(user, pk):
    return get_object_or_404(
        visible_agreements(user).prefetch_related("kpas__kpis", "appraisal__scores__kpi"),
        pk=pk,
    )


def get_area(user, pk):
    return get_object_or_404(
        KeyPerformanceArea.objects.filter(
            agreement__employee__in=visible_employees(user),
        ).select_related("agreement", "agreement__employee"),
        pk=pk,
    )


def get_indicator(user, pk):
    return get_object_or_404(
        KeyPerformanceIndicator.objects.filter(
            kpa__agreement__employee__in=visible_employees(user),
        ).select_related("kpa", "kpa__agreement", "kpa__agreement__employee"),
        pk=pk,
    )


def get_plan(user, pk):
    return get_object_or_404(
        ImprovementPlan.objects.filter(employee__in=visible_employees(user)).select_related("employee"),
        pk=pk,
    )


def get_skill(user, pk):
    return get_object_or_404(
        SkillAssessment.objects.filter(employee__in=visible_employees(user)).select_related("employee"),
        pk=pk,
    )


def get_development(user, pk):
    return get_object_or_404(
        DevelopmentPlan.objects.filter(employee__in=visible_employees(user)).select_related("employee"),
        pk=pk,
    )


def initial_employee(request):
    raw = request.GET.get("employee", "")
    if not raw.isdigit():
        return {}
    if visible_employees(request.user).filter(pk=int(raw)).exists():
        return {"employee": int(raw)}
    return {}


def structure_message(agreement):
    if agreement.status == AgreementStatus.CLOSED:
        return "A closed agreement cannot be changed."
    if agreement.status != AgreementStatus.DRAFT:
        return "KPAs and KPIs can be changed only while the agreement is a draft."
    return ""


def indicators_for(agreement):
    return (
        KeyPerformanceIndicator.objects.filter(kpa__agreement=agreement)
        .select_related("kpa")
        .order_by("kpa_id", "id")
    )


def remember_filer(record, user):
    if not record.filed_by_id:
        record.filed_by = user


@hr_login_required
def agreement_list(request):
    agreements = visible_agreements(request.user).prefetch_related("appraisal__scores__kpi")
    return render(request, "hr/performance_list.html", {"agreements": agreements})


@performance_editor_required
def agreement_create(request):
    form = AgreementForm(request.POST or None, user=request.user, initial=initial_employee(request))
    if request.method == "POST" and form.is_valid():
        agreement = form.save(commit=False)
        remember_filer(agreement, request.user)
        agreement.save()
        messages.success(request, "Agreement saved.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    return render(request, "hr/performance_form.html", {
        "form": form,
        "heading": "New agreement",
        "submit_label": "Save agreement",
    })


@hr_login_required
def agreement_detail(request, pk):
    agreement = get_agreement(request.user, pk)
    appraisal = getattr(agreement, "appraisal", None)
    return render(request, "hr/performance_detail.html", {
        "agreement": agreement,
        "areas": agreement.kpas.all(),
        "appraisal": appraisal,
        "weight_total": agreement.weight_total(),
    })


@performance_editor_required
def agreement_edit(request, pk):
    agreement = get_agreement(request.user, pk)
    if agreement.status == AgreementStatus.CLOSED:
        messages.error(request, "A closed agreement cannot be changed.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    form = AgreementForm(request.POST or None, instance=agreement, user=request.user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        remember_filer(saved, request.user)
        saved.save()
        messages.success(request, "Agreement saved.")
        return redirect("hr:agreement_detail", pk=saved.pk)
    return render(request, "hr/performance_form.html", {
        "form": form,
        "agreement": agreement,
        "heading": "Update agreement",
        "submit_label": "Save agreement",
    })


@performance_editor_required
def kpa_create(request, pk):
    agreement = get_agreement(request.user, pk)
    locked = structure_message(agreement)
    if locked:
        messages.error(request, locked)
        return redirect("hr:agreement_detail", pk=agreement.pk)
    form = KeyPerformanceAreaForm(request.POST or None)
    form.instance.agreement = agreement
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Key performance area saved.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    return render(request, "hr/kpa_form.html", {
        "form": form,
        "agreement": agreement,
        "heading": "Add key performance area",
        "submit_label": "Save key performance area",
    })


@performance_editor_required
def kpa_edit(request, pk):
    area = get_area(request.user, pk)
    locked = structure_message(area.agreement)
    if locked:
        messages.error(request, locked)
        return redirect("hr:agreement_detail", pk=area.agreement_id)
    form = KeyPerformanceAreaForm(request.POST or None, instance=area)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Key performance area saved.")
        return redirect("hr:agreement_detail", pk=area.agreement_id)
    return render(request, "hr/kpa_form.html", {
        "form": form,
        "agreement": area.agreement,
        "heading": "Edit key performance area",
        "submit_label": "Save key performance area",
    })


@performance_editor_required
def kpi_create(request, pk):
    area = get_area(request.user, pk)
    locked = structure_message(area.agreement)
    if locked:
        messages.error(request, locked)
        return redirect("hr:agreement_detail", pk=area.agreement_id)
    form = KeyPerformanceIndicatorForm(request.POST or None)
    form.instance.kpa = area
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Indicator saved.")
        return redirect("hr:agreement_detail", pk=area.agreement_id)
    return render(request, "hr/kpi_form.html", {
        "form": form,
        "agreement": area.agreement,
        "heading": "Add indicator",
        "submit_label": "Save indicator",
        "other_total": area.agreement.weight_total(),
    })


@performance_editor_required
def kpi_edit(request, pk):
    indicator = get_indicator(request.user, pk)
    agreement = indicator.kpa.agreement
    locked = structure_message(agreement)
    if locked:
        messages.error(request, locked)
        return redirect("hr:agreement_detail", pk=agreement.pk)
    form = KeyPerformanceIndicatorForm(request.POST or None, instance=indicator)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Indicator saved.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    others = agreement.weight_total() - indicator.weight
    return render(request, "hr/kpi_form.html", {
        "form": form,
        "agreement": agreement,
        "heading": "Edit indicator",
        "submit_label": "Save indicator",
        "other_total": others,
    })


@performance_editor_required
def appraisal_form(request, pk):
    agreement = get_agreement(request.user, pk)
    if agreement.status == AgreementStatus.CLOSED:
        messages.error(request, "A closed agreement cannot be changed.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    if agreement.status != AgreementStatus.ACTIVE:
        messages.error(request, "File the appraisal only when the agreement is active.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    kpis = list(indicators_for(agreement))
    if not kpis:
        messages.error(request, "Add the indicators before filing the appraisal.")
        return redirect("hr:agreement_detail", pk=agreement.pk)
    appraisal = Appraisal.objects.filter(agreement=agreement).first()
    initial = {}
    if appraisal is not None:
        initial = {
            "appraisal_date": appraisal.appraisal_date.isoformat(),
            "overall_comment": appraisal.overall_comment,
        }
        for row in appraisal.scores.all():
            initial[f"score_{row.kpi_id}"] = row.score
            initial[f"comment_{row.kpi_id}"] = row.comment
    form = AppraisalForm(request.POST or None, kpis=kpis, initial=None if request.method == "POST" else initial)
    if request.method == "POST" and form.is_valid():
        if appraisal is None:
            appraisal = Appraisal(agreement=agreement)
        appraisal.appraisal_date = form.cleaned_data["appraisal_date"]
        appraisal.overall_comment = form.cleaned_data["overall_comment"]
        remember_filer(appraisal, request.user)
        try:
            appraisal.full_clean()
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            with transaction.atomic():
                appraisal.save()
                for kpi in kpis:
                    AppraisalScore.objects.update_or_create(
                        appraisal=appraisal,
                        kpi=kpi,
                        defaults={
                            "score": form.cleaned_data[f"score_{kpi.pk}"],
                            "comment": form.cleaned_data[f"comment_{kpi.pk}"],
                        },
                    )
            messages.success(request, "Appraisal saved.")
            return redirect("hr:agreement_detail", pk=agreement.pk)
    return render(request, "hr/appraisal_form.html", {
        "form": form,
        "agreement": agreement,
        "heading": "File appraisal" if appraisal is None else "Update appraisal",
        "submit_label": "Save appraisal",
    })


@hr_login_required
def plan_list(request):
    plans = ImprovementPlan.objects.filter(
        employee__in=visible_employees(request.user),
    ).select_related("employee")
    return render(request, "hr/plan_list.html", {"plans": plans})


@performance_editor_required
def plan_create(request):
    form = ImprovementPlanForm(request.POST or None, user=request.user, initial=initial_employee(request))
    if request.method == "POST" and form.is_valid():
        plan = form.save(commit=False)
        remember_filer(plan, request.user)
        plan.save()
        messages.success(request, "Performance improvement plan saved.")
        return redirect("hr:plan_list")
    return render(request, "hr/plan_form.html", {
        "form": form,
        "heading": "Add performance improvement plan",
        "submit_label": "Save plan",
    })


@performance_editor_required
def plan_edit(request, pk):
    plan = get_plan(request.user, pk)
    form = ImprovementPlanForm(request.POST or None, instance=plan, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Performance improvement plan saved.")
        return redirect("hr:plan_list")
    return render(request, "hr/plan_form.html", {
        "form": form,
        "plan": plan,
        "heading": "Update performance improvement plan",
        "submit_label": "Save plan",
    })


@hr_login_required
def skill_list(request):
    skills = SkillAssessment.objects.filter(
        employee__in=visible_employees(request.user),
    ).select_related("employee")
    return render(request, "hr/skill_list.html", {"skills": skills})


@performance_editor_required
def skill_create(request):
    form = SkillAssessmentForm(request.POST or None, user=request.user, initial=initial_employee(request))
    if request.method == "POST" and form.is_valid():
        skill = form.save(commit=False)
        remember_filer(skill, request.user)
        skill.save()
        messages.success(request, "Skills assessment saved.")
        return redirect("hr:skill_list")
    return render(request, "hr/skill_form.html", {
        "form": form,
        "heading": "Add skills assessment",
        "submit_label": "Save assessment",
    })


@performance_editor_required
def skill_edit(request, pk):
    skill = get_skill(request.user, pk)
    form = SkillAssessmentForm(request.POST or None, instance=skill, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Skills assessment saved.")
        return redirect("hr:skill_list")
    return render(request, "hr/skill_form.html", {
        "form": form,
        "skill": skill,
        "heading": "Update skills assessment",
        "submit_label": "Save assessment",
    })


@hr_login_required
def development_list(request):
    plans = DevelopmentPlan.objects.filter(
        employee__in=visible_employees(request.user),
    ).select_related("employee")
    return render(request, "hr/development_list.html", {"plans": plans})


@performance_editor_required
def development_create(request):
    form = DevelopmentPlanForm(request.POST or None, user=request.user, initial=initial_employee(request))
    if request.method == "POST" and form.is_valid():
        plan = form.save(commit=False)
        remember_filer(plan, request.user)
        plan.save()
        messages.success(request, "Development plan saved.")
        return redirect("hr:development_list")
    return render(request, "hr/development_form.html", {
        "form": form,
        "heading": "Add development plan",
        "submit_label": "Save development plan",
    })


@performance_editor_required
def development_edit(request, pk):
    plan = get_development(request.user, pk)
    form = DevelopmentPlanForm(request.POST or None, instance=plan, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Development plan saved.")
        return redirect("hr:development_list")
    return render(request, "hr/development_form.html", {
        "form": form,
        "plan": plan,
        "heading": "Update development plan",
        "submit_label": "Save development plan",
    })
