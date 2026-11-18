from django.apps import AppConfig


class LeaveConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "leave"
    verbose_name = "Leave"

    def ready(self):
        from django.db.models.signals import post_save

        from company.models import Company
        from leave.models import ensure_leave_types

        post_save.connect(ensure_leave_types, sender=Company, dispatch_uid="leave.seed_types")
