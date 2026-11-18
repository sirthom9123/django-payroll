from django.contrib import admin

from leave.models import Attendance, LeaveApplication, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ["company", "name", "kind", "days_per_year", "accrual"]
    list_filter = ["kind", "company"]
    list_editable = ["days_per_year", "accrual"]
    search_fields = ["name", "company__company_name"]


@admin.register(LeaveApplication)
class LeaveApplicationAdmin(admin.ModelAdmin):
    list_display = ["employee", "leave_type", "start_date", "end_date", "days", "status"]
    list_filter = ["status", "leave_type"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__emp_code"]
    readonly_fields = ["days", "captured_by", "decided_by", "decided_at"]

    def save_model(self, request, obj, form, change):
        if not obj.captured_by_id:
            obj.captured_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["date", "employee", "status", "hours_worked", "recorded_by"]
    list_filter = ["status", "date"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__emp_code"]
    date_hierarchy = "date"
