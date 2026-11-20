from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from employee.models import Employee
from employee.tests import HrFixture
from recruitment.models import Application, ApplicationStatus, Vacancy, VacancyStatus


class RecruitmentFixture(HrFixture):
    def setUp(self):
        super().setUp()
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.manager = User.objects.create_user("manager.user", password=self.password, is_staff=True)
        self.manager.groups.add(self.manager_group)

    def vacancy_payload(self, **overrides):
        data = {
            "company": self.company.pk,
            "designation": self.designation.pk,
            "title": "Junior clerk",
            "description": "Front desk and filing.",
            "openings": "1",
            "closing_date": "",
            "status": "open",
        }
        data.update(overrides)
        return data

    def application_payload(self, **overrides):
        data = {
            "first_name": "Lerato",
            "last_name": "Dlamini",
            "email": "lerato@example.com",
            "phone": "0830000000",
            "id_number": "8001015009087",
            "passport": "",
            "applied_on": "2026-11-01",
            "status": "received",
            "note": "",
        }
        data.update(overrides)
        return data

    def open_vacancy(self, **overrides):
        self.client.force_login(self.hr)
        return self.client.post(reverse("hr:vacancy_create"), self.vacancy_payload(**overrides))


class RecruitmentAccessTests(RecruitmentFixture):
    def test_logged_out_user_is_sent_to_sign_in(self):
        response = self.client.get(reverse("hr:vacancy_list"))
        self.assertRedirects(response, "/accounts/login/?next=/hr/recruitment/")

    def test_non_staff_user_cannot_open_recruitment(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("hr:vacancy_list"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "You do not have access to HR.", status_code=403)

    def test_empty_list(self):
        self.client.force_login(self.hr)
        page = self.client.get(reverse("hr:vacancy_list"))
        self.assertContains(page, "No vacancies yet.")
        self.assertContains(page, "New vacancy")
        home = self.client.get(reverse("hr:home"))
        self.assertContains(home, "Open vacancies")
        self.assertContains(home, ">0<")

    def test_payroll_and_manager_can_view_and_cannot_change(self):
        self.open_vacancy()
        vacancy = Vacancy.objects.get()
        for user in (self.payroll_user, self.manager):
            self.client.force_login(user)
            listing = self.client.get(reverse("hr:vacancy_list"))
            self.assertContains(listing, "Junior clerk")
            self.assertNotContains(listing, "New vacancy")
            denied = self.client.post(reverse("hr:vacancy_create"), self.vacancy_payload(title="Another post"))
            self.assertEqual(denied.status_code, 403)
            self.assertContains(
                denied,
                "You can view recruitment records. Only HR can change them.",
                status_code=403,
            )
        self.assertEqual(Vacancy.objects.count(), 1)
        self.client.force_login(self.payroll_user)
        detail = self.client.get(reverse("hr:vacancy_detail", args=[vacancy.pk]))
        self.assertContains(detail, "No applications yet.")
        self.assertNotContains(detail, "Add application")

    def test_another_company_is_hidden(self):
        other = Company.objects.create(
            company_name="Other Co",
            owner=self.outsider,
            phone="0100000001",
            address="9 Other Road",
            email="other@example.com",
        )
        secret = Vacancy.objects.create(
            company=other,
            designation=self.designation,
            title="Hidden post",
            description="Not for this officer.",
            status=VacancyStatus.OPEN,
            created_by=self.outsider,
        )
        Application.objects.create(
            vacancy=secret,
            first_name="Hidden",
            last_name="Person",
            email="hidden@example.com",
            phone="0840000000",
            id_number="9001015009086",
            applied_on=timezone.localdate(),
            status=ApplicationStatus.RECEIVED,
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:vacancy_detail", args=[secret.pk]))
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(reverse("hr:vacancy_list"))
        self.assertNotContains(listing, "Hidden")
        application = Application.objects.get()
        missing = self.client.get(reverse("hr:application_detail", args=[application.pk]))
        self.assertEqual(missing.status_code, 404)

    def test_vacancy_admin_lists_the_title(self):
        self.open_vacancy()
        admin = User.objects.create_superuser("admin.user", "admin@example.com", self.password)
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:recruitment_vacancy_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Junior clerk")


class RecruitmentRecordTests(RecruitmentFixture):
    def test_hire_creates_an_employee_and_closes_a_single_opening(self):
        self.open_vacancy()
        vacancy = Vacancy.objects.get()
        self.assertEqual(vacancy.created_by, self.hr)
        added = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(),
        )
        application = Application.objects.get()
        self.assertRedirects(added, reverse("hr:application_detail", args=[application.pk]))
        self.assertEqual(application.filed_by, self.hr)
        self.assertEqual(application.email, "lerato@example.com")

        too_soon = self.client.get(reverse("hr:application_hire", args=[application.pk]))
        self.assertRedirects(too_soon, reverse("hr:application_detail", args=[application.pk]))
        self.assertEqual(Employee.objects.filter(email_address="lerato@example.com").count(), 0)

        offered = self.client.post(
            reverse("hr:application_edit", args=[application.pk]),
            self.application_payload(status="offered"),
        )
        self.assertRedirects(offered, reverse("hr:application_detail", args=[application.pk]))
        hired = self.client.post(reverse("hr:application_hire", args=[application.pk]), {
            "address": "4 Main Road",
            "country": "South Africa",
            "city": "Johannesburg",
            "postal_code": "2001",
            "date_hired": "2026-11-20",
        })
        employee = Employee.objects.get(email_address="lerato@example.com")
        self.assertRedirects(hired, reverse("hr:employee_detail", args=[employee.pk]))
        application.refresh_from_db()
        vacancy.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.HIRED)
        self.assertEqual(application.employee_id, employee.pk)
        self.assertEqual(employee.company, self.company)
        self.assertEqual(employee.designation, self.designation)
        self.assertEqual(employee.created_by, self.hr)
        self.assertEqual(employee.id_number, "8001015009087")
        self.assertEqual(employee.status, "Active")
        self.assertEqual(vacancy.status, VacancyStatus.CLOSED)

        page = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(page, "Junior clerk")
        self.assertContains(page, "Hired")
        other = self.client.get(reverse("hr:employee_detail", args=[self.create_employee()[1].pk]))
        self.assertContains(other, "This employee was not hired from a vacancy.")

        locked = self.client.get(reverse("hr:application_edit", args=[application.pk]))
        self.assertRedirects(locked, reverse("hr:application_detail", args=[application.pk]))
        self.assertEqual(Employee.objects.filter(email_address="lerato@example.com").count(), 1)

    def test_validation_and_a_second_opening(self):
        self.client.force_login(self.hr)
        draft = self.client.post(reverse("hr:vacancy_create"), self.vacancy_payload(status="draft"))
        vacancy = Vacancy.objects.get()
        self.assertRedirects(draft, reverse("hr:vacancy_detail", args=[vacancy.pk]))
        blocked = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(),
        )
        self.assertRedirects(blocked, reverse("hr:vacancy_detail", args=[vacancy.pk]))
        self.assertEqual(Application.objects.count(), 0)

        opened = self.client.post(
            reverse("hr:vacancy_edit", args=[vacancy.pk]),
            self.vacancy_payload(status="open", openings="2"),
        )
        self.assertRedirects(opened, reverse("hr:vacancy_detail", args=[vacancy.pk]))
        missing_identity = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(id_number="", passport=""),
        )
        self.assertContains(missing_identity, "Enter a 13-digit South African ID number, or a passport number.")
        bad_id = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(id_number="1234"),
        )
        self.assertContains(bad_id, "Enter a 13-digit South African ID number, or a passport number.")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        future = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(applied_on=tomorrow),
        )
        self.assertContains(future, "The application date cannot be in the future.")
        declined = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(status="declined", note=""),
        )
        self.assertContains(declined, "A decline needs a note.")
        self.assertEqual(Application.objects.count(), 0)

        self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(passport="A12345", id_number=""),
        )
        duplicate = self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(passport="a12345", id_number="", email="lerato@example.com"),
        )
        self.assertContains(duplicate, "This person has already applied for this vacancy.")
        self.assertEqual(Application.objects.count(), 1)
        application = Application.objects.get()
        self.assertEqual(application.passport, "A12345")
        self.client.post(
            reverse("hr:application_edit", args=[application.pk]),
            self.application_payload(passport="A12345", id_number="", status="offered"),
        )
        hired = self.client.post(reverse("hr:application_hire", args=[application.pk]), {
            "address": "8 Side Street",
            "country": "South Africa",
            "city": "Pretoria",
            "postal_code": "0002",
            "date_hired": "2026-11-20",
        })
        employee = Employee.objects.get(passport="A12345")
        self.assertRedirects(hired, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertFalse(employee.id_number)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, VacancyStatus.OPEN)

        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        stale = self.client.post(
            reverse("hr:vacancy_edit", args=[vacancy.pk]),
            self.vacancy_payload(status="open", openings="2", closing_date=past),
        )
        self.assertContains(stale, "The closing date has passed. Choose a later date or close the vacancy.")

        self.client.post(
            reverse("hr:vacancy_edit", args=[vacancy.pk]),
            self.vacancy_payload(status="closed", openings="2"),
        )
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, VacancyStatus.CLOSED)
        reopened = self.client.post(
            reverse("hr:vacancy_edit", args=[vacancy.pk]),
            self.vacancy_payload(status="open", openings="2"),
        )
        self.assertRedirects(reopened, reverse("hr:vacancy_detail", args=[vacancy.pk]))
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, VacancyStatus.CLOSED)

    def test_an_existing_id_number_is_not_hired_again(self):
        self.create_employee(id_number="8001015009087", email_address="thabo@example.com")
        self.open_vacancy(openings="1")
        vacancy = Vacancy.objects.get()
        self.client.post(
            reverse("hr:application_create", args=[vacancy.pk]),
            self.application_payload(status="offered"),
        )
        application = Application.objects.get(email="lerato@example.com")
        refused = self.client.post(reverse("hr:application_hire", args=[application.pk]), {
            "address": "4 Main Road",
            "country": "South Africa",
            "city": "Johannesburg",
            "postal_code": "2001",
            "date_hired": "2026-11-20",
        })
        self.assertContains(refused, "This ID number is already on an employee file.")
        self.assertEqual(Employee.objects.filter(id_number="8001015009087").count(), 1)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.OFFERED)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, VacancyStatus.OPEN)
