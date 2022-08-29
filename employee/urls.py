from django.urls import path

from . import views

urlpatterns = [
    path('employee/payroll/<int:id>/', views.admin_export_payroll_pdf, name='admin_export_payroll_pdf'),
]
