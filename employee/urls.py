from django.urls import include, path

from . import hr_views, payroll_views, views

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
    path("payroll/", payroll_views.payroll_list, name="payroll_list"),
    path("payroll/new/", payroll_views.payroll_create, name="payroll_create"),
    path("payroll/report/", payroll_views.payroll_report, name="payroll_report"),
    path("payroll/tax-years/", payroll_views.tax_year_list, name="tax_year_list"),
    path("payroll/tax-years/new/", payroll_views.tax_year_create, name="tax_year_create"),
    path("payroll/tax-years/<int:pk>/edit/", payroll_views.tax_year_edit, name="tax_year_edit"),
    path("payroll/<int:pk>/", payroll_views.payroll_detail, name="payroll_detail"),
    path("payroll/<int:pk>/edit/", payroll_views.payroll_edit, name="payroll_edit"),
    path("payroll/<int:pk>/payment/", payroll_views.payroll_payment, name="payroll_payment"),
    path("payroll/<int:pk>/payslip/", payroll_views.payroll_payslip, name="payroll_payslip"),
    path("", include("leave.urls")),
    path("", include("performance.urls")),
    path("", include("recruitment.urls")),
]

urlpatterns = [
    path('employee/payroll/<int:id>/', views.admin_export_payroll_pdf, name='admin_export_payroll_pdf'),
    path("hr/", include((hr_urlpatterns, "hr"))),
]
