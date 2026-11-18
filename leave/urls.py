from django.urls import path

from leave import views

urlpatterns = [
    path("leave/", views.leave_list, name="leave_list"),
    path("leave/new/", views.leave_create, name="leave_create"),
    path("leave/approvals/", views.leave_approvals, name="leave_approvals"),
    path("leave/<int:pk>/", views.leave_detail, name="leave_detail"),
    path("leave/<int:pk>/edit/", views.leave_edit, name="leave_edit"),
    path("leave/<int:pk>/cancel/", views.leave_cancel, name="leave_cancel"),
    path("leave/<int:pk>/decide/", views.leave_decide, name="leave_decide"),
    path("leave/<int:pk>/proof/", views.leave_proof, name="leave_proof"),
    path("attendance/", views.attendance_register, name="attendance"),
    path("attendance/timesheet/", views.timesheet, name="timesheet"),
]
