from django.contrib import admin
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import Benefits, Deduction, Department, Designation, Employee, Payroll, BankInfo

class BankInfoInline(admin.TabularInline):
    model = BankInfo

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["emp_code", "first_name", "last_name", "designation", "date_hired", "status", "employee_type", "created_by", "created"]
    list_display_links = ["emp_code",]
    list_filter = ["first_name", "last_name", "designation", "date_hired",]
    search_fields = ["first_name", "last_name", "designation", "date_hired", "created"]
    list_editable = ['status', 'employee_type']
    inlines = [BankInfoInline]
    
    
@admin.register(Benefits)
class BenefitsAdmin(admin.ModelAdmin):
    list_display = ["name", "amount"]
    list_filter = ["amount"]
    list_editable = ["amount",]
    
@admin.register(Deduction)
class DeductionAdmin(admin.ModelAdmin):
    list_display = ["name", "amount"]
    list_filter = ["amount"]
    list_editable = ["amount",]
    
    
def payroll_pdf(obj):
    url = reverse('admin_export_payroll_pdf', args=[obj.id])
    return mark_safe(f'<a href="{url}" target="_blank">View</a>')
payroll_pdf.short_description = 'Export Payslip'    
    
@admin.register(Payroll)    
class PayrollAdmin(admin.ModelAdmin):
    list_display = ["employee", "basic_salary", "rate", "hours", "income_tax", "uif_contribution", "created_by", payroll_pdf]
    list_filter = ["employee", "basic_salary", "rate", "created_by"]
    search_fields = ["employee", "basic_salary", "rate",]
    list_display_links = ["employee",]
    
    
admin.site.register(Department)
admin.site.register(Designation)