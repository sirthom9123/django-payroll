from django.urls import include, path

from . import hr_views, views

hr_urlpatterns = [
    path("", hr_views.home, name="home"),
    path("continue/", hr_views.after_login, name="after_login"),
    path("no-access/", hr_views.no_access, name="no_access"),
    path("employees/", hr_views.employee_list, name="employee_list"),
    path("employees/new/", hr_views.employee_create, name="employee_create"),
    path("employees/<int:pk>/", hr_views.employee_detail, name="employee_detail"),
    path("employees/<int:pk>/edit/", hr_views.employee_edit, name="employee_edit"),
    path("employees/<int:pk>/contract/", hr_views.contract_form, name="contract_form"),
    path("employees/<int:pk>/qualifications/new/", hr_views.qualification_create, name="qualification_create"),
    path("employees/<int:pk>/qualifications/<int:qualification_pk>/edit/", hr_views.qualification_edit, name="qualification_edit"),
    path("employees/<int:pk>/history/new/", hr_views.history_create, name="history_create"),
    path("employees/<int:pk>/history/<int:history_pk>/edit/", hr_views.history_edit, name="history_edit"),
    path("employees/<int:pk>/documents/new/", hr_views.document_create, name="document_create"),
    path("documents/<int:pk>/download/", hr_views.document_download, name="document_download"),
]

urlpatterns = [
    path('employee/payroll/<int:id>/', views.admin_export_payroll_pdf, name='admin_export_payroll_pdf'),
    path("hr/", include((hr_urlpatterns, "hr"))),
]
