from django.urls import path

from performance import views

urlpatterns = [
    path("performance/", views.agreement_list, name="agreement_list"),
    path("performance/new/", views.agreement_create, name="agreement_create"),
    path("performance/plans/", views.plan_list, name="plan_list"),
    path("performance/plans/new/", views.plan_create, name="plan_create"),
    path("performance/plans/<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("performance/skills/", views.skill_list, name="skill_list"),
    path("performance/skills/new/", views.skill_create, name="skill_create"),
    path("performance/skills/<int:pk>/edit/", views.skill_edit, name="skill_edit"),
    path("performance/development/", views.development_list, name="development_list"),
    path("performance/development/new/", views.development_create, name="development_create"),
    path("performance/development/<int:pk>/edit/", views.development_edit, name="development_edit"),
    path("performance/<int:pk>/", views.agreement_detail, name="agreement_detail"),
    path("performance/<int:pk>/edit/", views.agreement_edit, name="agreement_edit"),
    path("performance/<int:pk>/kpa/new/", views.kpa_create, name="kpa_create"),
    path("performance/<int:pk>/appraise/", views.appraisal_form, name="appraisal_form"),
    path("performance/kpa/<int:pk>/edit/", views.kpa_edit, name="kpa_edit"),
    path("performance/kpa/<int:pk>/kpi/new/", views.kpi_create, name="kpi_create"),
    path("performance/kpi/<int:pk>/edit/", views.kpi_edit, name="kpi_edit"),
]
