from django.contrib import admin

from recruitment.models import Application, Vacancy


class ApplicationInline(admin.TabularInline):
    model = Application
    extra = 0
    fields = ["first_name", "last_name", "email", "status", "applied_on", "employee"]
    readonly_fields = ["employee"]
    show_change_link = True


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "designation", "status", "openings", "closing_date"]
    list_filter = ["status", "company"]
    search_fields = ["title", "company__company_name"]
    readonly_fields = ["created_by"]
    inlines = [ApplicationInline]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "vacancy", "status", "applied_on", "employee"]
    list_filter = ["status"]
    search_fields = ["first_name", "last_name", "email", "id_number", "passport"]
    readonly_fields = ["filed_by", "employee"]
