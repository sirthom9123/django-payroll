from django.urls import path

from recruitment import views

urlpatterns = [
    path("recruitment/", views.vacancy_list, name="vacancy_list"),
    path("recruitment/new/", views.vacancy_create, name="vacancy_create"),
    path("recruitment/<int:pk>/", views.vacancy_detail, name="vacancy_detail"),
    path("recruitment/<int:pk>/edit/", views.vacancy_edit, name="vacancy_edit"),
    path("recruitment/<int:pk>/applications/new/", views.application_create, name="application_create"),
    path("recruitment/applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("recruitment/applications/<int:pk>/edit/", views.application_edit, name="application_edit"),
    path("recruitment/applications/<int:pk>/hire/", views.application_hire, name="application_hire"),
]
