def latest_skills(employee):
    """The newest assessment for each skill name. Spelling of the latest row is kept."""
    seen = {}
    rows = employee.skill_assessments.order_by("-assessed_on", "-id")
    for row in rows:
        key = row.skill.casefold()
        if key not in seen:
            seen[key] = row
    return sorted(seen.values(), key=lambda row: row.skill.casefold())


def file_summary(employee):
    agreements = (
        employee.performance_agreements
        .select_related("appraisal")
        .prefetch_related("kpas__kpis", "appraisal__scores__kpi")
    )
    return {
        "performance_agreements": agreements,
        "improvement_plans": employee.improvement_plans.all(),
        "skill_assessments": latest_skills(employee),
        "development_plans": employee.development_plans.all(),
    }
