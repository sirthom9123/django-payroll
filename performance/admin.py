from django.contrib import admin

from performance.models import (
    Agreement,
    Appraisal,
    AppraisalScore,
    DevelopmentPlan,
    ImprovementPlan,
    KeyPerformanceArea,
    KeyPerformanceIndicator,
    SkillAssessment,
)


class KeyPerformanceAreaInline(admin.TabularInline):
    model = KeyPerformanceArea
    extra = 0


class AppraisalScoreInline(admin.TabularInline):
    model = AppraisalScore
    extra = 0


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ["employee", "cycle", "status", "filed_by"]
    list_filter = ["status", "cycle"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__emp_code", "cycle"]
    readonly_fields = ["filed_by"]
    inlines = [KeyPerformanceAreaInline]


@admin.register(KeyPerformanceIndicator)
class KeyPerformanceIndicatorAdmin(admin.ModelAdmin):
    list_display = ["name", "kpa", "measure", "weight"]
    search_fields = ["name", "measure"]


@admin.register(Appraisal)
class AppraisalAdmin(admin.ModelAdmin):
    list_display = ["agreement", "appraisal_date", "filed_by"]
    readonly_fields = ["filed_by"]
    inlines = [AppraisalScoreInline]


@admin.register(ImprovementPlan)
class ImprovementPlanAdmin(admin.ModelAdmin):
    list_display = ["employee", "start_date", "review_date", "outcome"]
    list_filter = ["outcome"]
    search_fields = ["employee__first_name", "employee__last_name", "concern"]


@admin.register(SkillAssessment)
class SkillAssessmentAdmin(admin.ModelAdmin):
    list_display = ["employee", "skill", "level", "assessed_on"]
    search_fields = ["skill", "employee__first_name", "employee__last_name"]


@admin.register(DevelopmentPlan)
class DevelopmentPlanAdmin(admin.ModelAdmin):
    list_display = ["employee", "skill_gap", "due_date", "status"]
    list_filter = ["status"]
    search_fields = ["skill_gap", "employee__first_name", "employee__last_name"]
