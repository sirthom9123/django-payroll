import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from employee.models import (
    AllowanceLine,
    BankInfo,
    Benefits,
    Contract,
    DeductionLine,
    Department,
    Designation,
    Employee,
    EmployeeDocument,
    EmploymentHistory,
    Payroll,
    PayrollPayment,
    Qualification,
    Status,
    TaxYear,
    hr_document_storage,
)
from employee.payroll_math import annual_tax


class HrFixture(TestCase):
    password = "test-pass-123"

    def setUp(self):
        self.hr_group, _ = Group.objects.get_or_create(name="HR")
        self.pay_group, _ = Group.objects.get_or_create(name="Payroll")
        self.hr = User.objects.create_user("hr.user", password=self.password, is_staff=True)
        self.hr.groups.add(self.hr_group)
        self.payroll_user = User.objects.create_user("pay.user", password=self.password, is_staff=True)
        self.payroll_user.groups.add(self.pay_group)
        self.outsider = User.objects.create_user("outsider", password=self.password, is_staff=True)
        self.plain = User.objects.create_user("plain.user", password=self.password, is_staff=False)
        self.department = Department.objects.create(name="Operations")
        self.other_department = Department.objects.create(name="Finance")
        self.designation = Designation.objects.create(department=self.department, name="Clerk")
        self.other_designation = Designation.objects.create(department=self.other_department, name="Bookkeeper")
        self.company = Company.objects.create(
            company_name="Yehuda Test",
            owner=self.hr,
            phone="0100000000",
            address="1 Test Street",
            email="hr@example.com",
        )
        self.document_dir = tempfile.mkdtemp()
        self.previous_document_location = hr_document_storage.location
        hr_document_storage.location = self.document_dir

    def tearDown(self):
        hr_document_storage.location = self.previous_document_location
        shutil.rmtree(self.document_dir, ignore_errors=True)

    def employee_payload(self, **overrides):
        data = {
            "company": self.company.pk,
            "emp_code": "",
            "first_name": "Thabo",
            "middle_name": "",
            "last_name": "Mokoena",
            "maiden_name": "",
            "id_number": "1234567890123",
            "passport": "",
            "email_address": "thabo@example.com",
            "phone": "0820000000",
            "alt_phone": "",
            "address": "2 Test Road",
            "country": "South Africa",
            "city": "Johannesburg",
            "postal_code": "2000",
            "designation": self.designation.pk,
            "date_hired": "2024-03-01",
            "date_departed": "",
            "gross_salary": "",
            "hourly_rate": "",
            "pension_number": "",
            "employee_type": "Full-Time",
            "status": "Active",
        }
        data.update(overrides)
        return data

    def create_employee(self, **overrides):
        self.client.force_login(self.hr)
        response = self.client.post(reverse("hr:employee_create"), self.employee_payload(**overrides))
        employee = Employee.objects.get(email_address=overrides.get("email_address", "thabo@example.com"))
        return response, employee


class HrAccessTests(HrFixture):
    def test_logged_out_user_is_sent_to_sign_in(self):
        response = self.client.get(reverse("hr:home"))
        self.assertRedirects(response, "/accounts/login/?next=/hr/")

    def test_root_shows_sign_in(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_hr_user_lands_on_hr_home_after_sign_in(self):
        response = self.client.post(reverse("login"), {
            "username": "hr.user",
            "password": self.password,
        }, follow=True)
        self.assertContains(response, "HR home")
        self.assertEqual(response.request["PATH_INFO"], "/hr/")

    def test_staff_without_a_group_sees_no_access(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("hr:home"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "You do not have access to HR.", status_code=403)

    def test_non_staff_user_sees_no_access(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("hr:employee_list"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "You do not have access to HR.", status_code=403)

    def test_navigation_sits_in_a_side_column(self):
        self.client.force_login(self.hr)
        home = self.client.get(reverse("hr:home"))
        self.assertContains(home, 'class="side"')
        self.assertContains(home, 'href="/hr/" aria-current="page"')
        employees = self.client.get(reverse("hr:employee_list"))
        self.assertContains(employees, 'href="/hr/employees/" aria-current="page"')
        self.assertNotContains(employees, 'href="/hr/" aria-current="page"')

    def test_hr_stylesheet_lives_in_project_static(self):
        found = finders.find("hr/hr.css")
        expected = os.path.join(settings.STATIC_ROOT, "hr", "hr.css")
        self.assertTrue(os.path.isfile(expected))
        self.assertTrue(os.path.samefile(found, expected))
        self.client.force_login(self.hr)
        page = self.client.get(reverse("hr:home"))
        self.assertContains(page, "/static/hr/hr.css")

    def test_empty_employee_list(self):
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:employee_list"))
        self.assertContains(response, "No employees yet.")
        self.assertContains(response, "Add employee")


class EmployeeRecordTests(HrFixture):
    def test_hr_can_add_a_person_and_the_rest_of_the_file(self):
        response, employee = self.create_employee()
        self.assertRedirects(response, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(employee.created_by, self.hr)
        self.assertEqual(employee.company, self.company)
        self.assertTrue(employee.emp_code)
        self.assertNotIn("None", employee.emp_code)
        code = employee.emp_code
        edited = self.client.post(
            reverse("hr:employee_edit", args=[employee.pk]),
            self.employee_payload(emp_code=code, phone="0830000000"),
        )
        self.assertRedirects(edited, reverse("hr:employee_detail", args=[employee.pk]))
        employee.refresh_from_db()
        self.assertEqual(employee.emp_code, code)
        self.assertEqual(employee.phone, "0830000000")

        contract = self.client.post(reverse("hr:contract_form", args=[employee.pk]), {
            "contract_type": "permanent",
            "start_date": "2024-03-01",
            "end_date": "",
            "job_title": "Clerk",
            "job_description": "Keeps the employee file.",
            "notice_period_days": "30",
            "signed_date": "2024-03-01",
        })
        self.assertRedirects(contract, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(Contract.objects.filter(employee=employee, is_current=True).count(), 1)

        replacement = self.client.post(
            reverse("hr:contract_form", args=[employee.pk]) + "?new=1",
            {
                "contract_type": "fixed-term",
                "start_date": "2026-03-01",
                "end_date": "2027-02-28",
                "job_title": "Senior clerk",
                "job_description": "Runs the file.",
                "notice_period_days": "14",
                "signed_date": "2026-02-20",
                "replace": "1",
            },
        )
        self.assertRedirects(replacement, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(employee.contracts.count(), 2)
        self.assertEqual(employee.contracts.filter(is_current=True).get().job_title, "Senior clerk")

        qualification = self.client.post(reverse("hr:qualification_create", args=[employee.pk]), {
            "institution": "UNISA",
            "name": "BCom",
            "year_completed": "2018",
            "nqf_level": "7",
        })
        self.assertRedirects(qualification, reverse("hr:employee_detail", args=[employee.pk]))
        second = self.client.post(reverse("hr:qualification_create", args=[employee.pk]), {
            "institution": "College of Cape Town",
            "name": "Certificate",
            "year_completed": "2014",
            "nqf_level": "",
        })
        self.assertRedirects(second, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(Qualification.objects.filter(employee=employee).count(), 2)

        history = self.client.post(reverse("hr:history_create", args=[employee.pk]), {
            "employer": "Old Farm",
            "role": "Assistant",
            "start_date": "2016-01-01",
            "end_date": "2020-12-31",
            "reason_for_leaving": "Relocated",
        })
        self.assertRedirects(history, reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(EmploymentHistory.objects.filter(employee=employee).count(), 1)

        upload = self.client.post(reverse("hr:document_create", args=[employee.pk]), {
            "title": "ID copy",
            "document_type": "id-copy",
            "file": SimpleUploadedFile("id-copy.txt", b"sample-document", content_type="text/plain"),
        })
        self.assertRedirects(upload, reverse("hr:employee_detail", args=[employee.pk]))
        document = EmployeeDocument.objects.get(employee=employee)
        download = self.client.get(reverse("hr:document_download", args=[document.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"sample-document")
        self.assertIn("attachment", download["Content-Disposition"])

        BankInfo.objects.create(
            employee=employee,
            account_number="998877665544",
            name="Test Bank",
            branch_name="Sandton",
            branch_code="123456",
        )
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "Thabo")
        self.assertContains(detail, "Senior clerk")
        self.assertContains(detail, "BCom")
        self.assertContains(detail, "Old Farm")
        self.assertContains(detail, "ID copy")
        self.assertContains(detail, "•••• 5544")
        self.assertNotContains(detail, "998877665544")
        self.assertContains(detail, "Annual leave")
        self.assertContains(detail, "Entitled")

    def test_list_search_and_filters(self):
        _, first = self.create_employee()
        _, second = self.create_employee(
            first_name="Lerato",
            last_name="Nkosi",
            email_address="lerato@example.com",
            designation=self.other_designation.pk,
            status="Suspended",
            employee_type="Part-Time",
        )
        self.client.force_login(self.hr)
        by_name = self.client.get(reverse("hr:employee_list"), {"q": "Nkosi"})
        self.assertContains(by_name, "Lerato")
        self.assertNotContains(by_name, "Thabo")
        by_code = self.client.get(reverse("hr:employee_list"), {"q": first.emp_code})
        self.assertContains(by_code, "Thabo")
        self.assertNotContains(by_code, "Lerato")
        by_department = self.client.get(reverse("hr:employee_list"), {"department": self.department.pk})
        self.assertContains(by_department, "Thabo")
        self.assertNotContains(by_department, "Lerato")
        by_status = self.client.get(reverse("hr:employee_list"), {"status": "Suspended"})
        self.assertContains(by_status, "Lerato")
        self.assertNotContains(by_status, "Thabo")
        self.assertNotEqual(first.emp_code, second.emp_code)

    def test_validation_for_identity_dates_and_contract(self):
        self.client.force_login(self.hr)
        missing_identity = self.client.post(reverse("hr:employee_create"), self.employee_payload(
            id_number="",
            passport="",
        ))
        self.assertEqual(missing_identity.status_code, 200)
        self.assertContains(
            missing_identity,
            "Enter a 13-digit South African ID number, or a passport number.",
        )
        self.assertEqual(Employee.objects.count(), 0)

        bad_id = self.client.post(reverse("hr:employee_create"), self.employee_payload(id_number="1234"))
        self.assertContains(
            bad_id,
            "Enter a 13-digit South African ID number, or a passport number.",
        )

        departed = self.client.post(reverse("hr:employee_create"), self.employee_payload(
            date_departed="2020-01-01",
        ))
        self.assertContains(departed, "Date departed cannot be before date hired.")
        self.assertEqual(Employee.objects.count(), 0)

        passport_only = self.client.post(reverse("hr:employee_create"), self.employee_payload(
            id_number="",
            passport="A12345678",
        ))
        self.assertEqual(passport_only.status_code, 302)
        self.assertEqual(Employee.objects.get().passport, "A12345678")

        employee = Employee.objects.get()
        fixed_term = self.client.post(reverse("hr:contract_form", args=[employee.pk]), {
            "contract_type": "fixed-term",
            "start_date": "2024-03-01",
            "end_date": "",
            "job_title": "Intern",
            "job_description": "",
            "notice_period_days": "7",
            "signed_date": "",
        })
        self.assertEqual(fixed_term.status_code, 200)
        self.assertContains(fixed_term, "End date is required for a fixed-term contract.")
        self.assertEqual(Contract.objects.count(), 0)

        history = self.client.post(reverse("hr:history_create", args=[employee.pk]), {
            "employer": "Old Farm",
            "role": "Assistant",
            "start_date": "2020-01-01",
            "end_date": "2019-01-01",
            "reason_for_leaving": "",
        })
        self.assertContains(history, "End date cannot be before the start date.")
        self.assertEqual(EmploymentHistory.objects.count(), 0)

    def test_home_counts_use_the_johannesburg_month(self):
        _, employee = self.create_employee()
        Employee.objects.create(
            first_name="Suspended",
            last_name="Person",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            status=Status.SUSPENDED,
            emp_code="SUS001",
        )
        today = timezone.localdate()
        Payroll.objects.create(
            employee=employee,
            rate=Decimal("100.00"),
            hours=Decimal("8"),
            income_tax=Decimal("10.00"),
            start_date=today,
            created_by=self.hr,
        )
        Payroll.objects.create(
            employee=employee,
            rate=Decimal("100.00"),
            hours=Decimal("8"),
            income_tax=Decimal("10.00"),
            start_date=today.replace(year=today.year - 1),
            created_by=self.hr,
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:home"))
        self.assertContains(response, '<p class="count">1</p>', count=2)
        self.assertContains(response, "Open leave")
        self.assertContains(response, '<p class="count">0</p>')

    def test_other_company_file_is_not_visible(self):
        other_company = Company.objects.create(
            company_name="Other Co",
            owner=self.outsider,
            phone="0100000001",
            address="9 Other Road",
            email="other@example.com",
        )
        hidden = Employee.objects.create(
            first_name="Hidden",
            last_name="Person",
            designation=self.designation,
            company=other_company,
            created_by=self.outsider,
            emp_code="HID001",
            status=Status.ACTIVE,
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:employee_detail", args=[hidden.pk]))
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(reverse("hr:employee_list"))
        self.assertNotContains(listing, "Hidden")


class PayrollReadOnlyTests(HrFixture):
    def test_payroll_can_open_the_file_but_cannot_edit_it(self):
        _, employee = self.create_employee()
        self.client.force_login(self.payroll_user)
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Edit employee")
        self.assertContains(detail, "Thabo")

        edit = self.client.get(reverse("hr:employee_edit", args=[employee.pk]))
        self.assertEqual(edit.status_code, 403)
        self.assertContains(edit, "Only HR can change it.", status_code=403)

        posted = self.client.post(
            reverse("hr:employee_edit", args=[employee.pk]),
            self.employee_payload(first_name="Changed"),
        )
        self.assertEqual(posted.status_code, 403)
        employee.refresh_from_db()
        self.assertEqual(employee.first_name, "Thabo")

        upload = self.client.post(reverse("hr:document_create", args=[employee.pk]), {
            "title": "ID copy",
            "document_type": "id-copy",
            "file": SimpleUploadedFile("id-copy.txt", b"sample-document", content_type="text/plain"),
        })
        self.assertEqual(upload.status_code, 403)
        self.assertEqual(EmployeeDocument.objects.count(), 0)

    def test_anonymous_document_download_goes_to_sign_in(self):
        _, employee = self.create_employee()
        self.client.force_login(self.hr)
        self.client.post(reverse("hr:document_create", args=[employee.pk]), {
            "title": "ID copy",
            "document_type": "id-copy",
            "file": SimpleUploadedFile("id-copy.txt", b"sample-document", content_type="text/plain"),
        })
        document = EmployeeDocument.objects.get()
        self.client.logout()
        response = self.client.get(reverse("hr:document_download", args=[document.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertFalse(os.path.basename(document.file.name).startswith("http"))


class PayslipUnchangedTests(HrFixture):
    def test_basic_salary_and_uif_rules_are_unchanged(self):
        employee = Employee.objects.create(
            first_name="Pay",
            last_name="Test",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="PAY001",
        )
        rate = Decimal("250.50")
        hours = Decimal("10")
        payroll = Payroll.objects.create(
            employee=employee,
            rate=rate,
            hours=hours,
            income_tax=Decimal("100.00"),
            start_date=timezone.localdate(),
            created_by=self.hr,
        )
        payroll.refresh_from_db()
        self.assertEqual(payroll.basic_salary, Decimal("2505.00"))
        stored_uif = (rate * hours * Decimal("0.01")).quantize(Decimal("0.01"))
        self.assertEqual(payroll.uif_contribution, stored_uif)
        self.assertEqual(payroll.overtime_amount, Decimal("0.00"))
        benefit = Benefits.objects.create(name="Housing", amount=Decimal("15.00"))
        payroll.benefits.add(benefit)
        self.assertEqual(payroll.get_gross_salary, Decimal("2520.00"))
        self.assertEqual(payroll.income_tax, Decimal("0.00"))
        self.assertEqual(payroll.get_nett_salary, Decimal("2494.95"))
        self.assertEqual(payroll.uif_contribution, stored_uif)

    def test_payslip_pdf_stays_staff_only(self):
        employee = Employee.objects.create(
            first_name="Pay",
            last_name="Test",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="PAY002",
        )
        payroll = Payroll.objects.create(
            employee=employee,
            rate=Decimal("100.00"),
            hours=Decimal("8"),
            income_tax=Decimal("50.00"),
            start_date=timezone.localdate(),
            created_by=self.hr,
        )
        anonymous = self.client.get(reverse("admin_export_payroll_pdf", args=[payroll.pk]))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/admin/login/", anonymous["Location"])

        self.client.force_login(self.plain)
        non_staff = self.client.get(reverse("admin_export_payroll_pdf", args=[payroll.pk]))
        self.assertEqual(non_staff.status_code, 302)

        self.client.force_login(self.hr)
        staff = self.client.get(reverse("admin_export_payroll_pdf", args=[payroll.pk]))
        self.assertEqual(staff.status_code, 200)
        self.assertEqual(staff["Content-Type"], "application/pdf")
        self.assertTrue(staff.content.startswith(b"%PDF"))
        html = render_to_string("payroll.html", {"payroll": payroll})
        self.assertNotIn("Overtime pay", html)
        self.assertNotIn("Allowance", html)

        self.client.force_login(self.outsider)
        outsider = self.client.get(reverse("admin_export_payroll_pdf", args=[payroll.pk]))
        self.assertEqual(outsider.status_code, 403)


def _line_data(prefix, rows):
    total = len(rows) + 1
    data = {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for index, (name, amount) in enumerate(rows):
        data[f"{prefix}-{index}-id"] = ""
        data[f"{prefix}-{index}-name"] = name
        data[f"{prefix}-{index}-amount"] = str(amount)
        data[f"{prefix}-{index}-DELETE"] = ""
    blank = len(rows)
    data[f"{prefix}-{blank}-id"] = ""
    data[f"{prefix}-{blank}-name"] = ""
    data[f"{prefix}-{blank}-amount"] = ""
    data[f"{prefix}-{blank}-DELETE"] = ""
    return data


class PayrollRunTests(HrFixture):
    def payroll_payload(self, employee, **overrides):
        data = {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "rate": "100.00",
            "hours": "10.00",
            "overtime_hours": "5.00",
            "overtime_rate": "200.00",
            "income_tax": "100.00",
        }
        data.update(_line_data("allowances", [("Travel", "50.00")]))
        data.update(_line_data("deductions", [("Staff loan", "25.00")]))
        data.update(overrides)
        return data

    def test_logged_out_and_non_staff_cannot_open_payroll(self):
        anonymous = self.client.get(reverse("hr:payroll_list"))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/accounts/login/", anonymous["Location"])

        self.client.force_login(self.plain)
        denied = self.client.get(reverse("hr:payroll_list"))
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "No access", status_code=403)
        posted = self.client.post(reverse("hr:payroll_create"), {})
        self.assertEqual(posted.status_code, 403)
        self.assertEqual(Payroll.objects.count(), 0)

        self.client.force_login(self.outsider)
        outsider = self.client.get(reverse("hr:payroll_list"))
        self.assertEqual(outsider.status_code, 403)
        self.assertContains(outsider, "No access", status_code=403)

    def test_hr_cannot_run_payroll(self):
        _, employee = self.create_employee()
        self.client.force_login(self.hr)
        denied = self.client.get(reverse("hr:payroll_list"))
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "Payroll group", status_code=403)
        home = self.client.get(reverse("hr:home"))
        self.assertNotContains(home, 'href="/hr/payroll/"')
        posted = self.client.post(reverse("hr:payroll_create"), self.payroll_payload(employee))
        self.assertEqual(posted.status_code, 403)
        self.assertEqual(Payroll.objects.count(), 0)

    def test_officer_saves_overtime_lines_payment_and_report(self):
        _, employee = self.create_employee(employee_type="Contract", hourly_rate="100.00")
        self.client.force_login(self.payroll_user)
        created = self.client.post(reverse("hr:payroll_create"), self.payroll_payload(employee))
        payroll = Payroll.objects.get()
        self.assertRedirects(created, reverse("hr:payroll_detail", args=[payroll.pk]))
        payroll.refresh_from_db()
        self.assertEqual(payroll.basic_salary, Decimal("1000.00"))
        self.assertEqual(payroll.uif_contribution, Decimal("10.00"))
        self.assertEqual(payroll.overtime_amount, Decimal("1000.00"))
        self.assertEqual(payroll.allowance_total, Decimal("50.00"))
        self.assertEqual(payroll.deduction_line_total, Decimal("25.00"))
        self.assertEqual(payroll.get_gross_salary, Decimal("2050.00"))
        self.assertEqual(payroll.income_tax, Decimal("0.00"))
        self.assertEqual(payroll.get_total_deductions, Decimal("35.00"))
        self.assertEqual(payroll.get_nett_salary, Decimal("2015.00"))
        self.assertEqual(AllowanceLine.objects.count(), 1)
        self.assertEqual(DeductionLine.objects.count(), 1)

        detail = self.client.get(reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertContains(detail, "R2015.00")
        self.assertContains(detail, "2026/27")
        self.assertContains(detail, "Unpaid")
        self.assertContains(detail, "Travel")

        short = self.client.post(reverse("hr:payroll_payment", args=[payroll.pk]), {
            "method": "eft",
            "payment_date": "2026-03-31",
            "reference": "EFT-1",
            "amount": "1914.99",
        })
        self.assertEqual(short.status_code, 200)
        self.assertContains(short, "Amount must equal the nett salary (R2015.00).")
        self.assertEqual(PayrollPayment.objects.count(), 0)

        paid = self.client.post(reverse("hr:payroll_payment", args=[payroll.pk]), {
            "method": "eft",
            "payment_date": "2026-03-31",
            "reference": "EFT-1",
            "amount": "2015.00",
        })
        self.assertRedirects(paid, reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertEqual(PayrollPayment.objects.get().amount, Decimal("2015.00"))

        listing = self.client.get(reverse("hr:payroll_list"))
        self.assertContains(listing, "Paid")
        self.assertContains(listing, "R2050.00")

        locked = self.client.post(
            reverse("hr:payroll_edit", args=[payroll.pk]),
            self.payroll_payload(employee, rate="999.00"),
        )
        self.assertRedirects(locked, reverse("hr:payroll_detail", args=[payroll.pk]))
        payroll.refresh_from_db()
        self.assertEqual(payroll.rate, Decimal("100.00"))

        report = self.client.get(reverse("hr:payroll_report"), {
            "company": self.company.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        })
        self.assertContains(report, "Headcount")
        self.assertContains(report, "<dd>1</dd>")
        self.assertContains(report, "R2050.00")
        self.assertContains(report, "R0.00")
        self.assertContains(report, "R10.00")
        self.assertContains(report, "R2015.00")

        html = render_to_string("payroll.html", {"payroll": payroll})
        self.assertIn("Overtime pay", html)
        self.assertIn("Travel", html)
        self.assertIn("Staff loan", html)
        slip = self.client.get(reverse("hr:payroll_payslip", args=[payroll.pk]))
        self.assertEqual(slip.status_code, 200)
        self.assertEqual(slip["Content-Type"], "application/pdf")
        self.assertTrue(slip.content.startswith(b"%PDF"))

    def test_uif_rounds_half_up_and_ignores_overtime(self):
        employee = Employee.objects.create(
            first_name="Round",
            last_name="Test",
            designation=self.designation,
            company=self.company,
            created_by=self.payroll_user,
            emp_code="RND001",
        )
        payroll = Payroll.objects.create(
            employee=employee,
            rate=Decimal("10.50"),
            hours=Decimal("1.00"),
            overtime_hours=Decimal("1.00"),
            overtime_rate=Decimal("10.50"),
            income_tax=Decimal("0.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            created_by=self.payroll_user,
        )
        payroll.refresh_from_db()
        self.assertEqual(payroll.basic_salary, Decimal("10.50"))
        self.assertEqual(payroll.uif_contribution, Decimal("0.11"))
        self.assertEqual(payroll.overtime_amount, Decimal("10.50"))
        self.assertEqual(payroll.get_gross_salary, Decimal("21.00"))

    def test_period_and_overtime_rate_are_validated(self):
        _, employee = self.create_employee()
        self.client.force_login(self.payroll_user)
        response = self.client.post(reverse("hr:payroll_create"), self.payroll_payload(
            employee,
            end_date="2026-02-01",
            overtime_hours="2.00",
            overtime_rate="0.00",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "End date must be on or after the start date.")
        self.assertContains(response, "Enter an overtime rate.")
        self.assertEqual(Payroll.objects.count(), 0)

    def test_run_without_a_tax_year_is_refused(self):
        _, employee = self.create_employee()
        self.client.force_login(self.payroll_user)
        response = self.client.post(reverse("hr:payroll_create"), self.payroll_payload(
            employee,
            start_date="2025-06-01",
            end_date="2025-06-30",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is no PAYE table for this date.")
        self.assertEqual(Payroll.objects.count(), 0)

    def test_one_run_can_hold_several_allowances_and_deductions(self):
        _, employee = self.create_employee(
            email_address="lines@example.com",
            emp_code="LIN001",
            employee_type="Contract",
            hourly_rate="100.00",
        )
        self.client.force_login(self.payroll_user)
        form = self.client.get(reverse("hr:payroll_create"))
        self.assertContains(form, "Add another allowance")
        self.assertContains(form, "Add another deduction")
        data = self.payroll_payload(employee)
        data.update(_line_data("allowances", [("Travel", "50.00"), ("Phone", "20.00")]))
        data.update(_line_data("deductions", [("Staff loan", "25.00"), ("Union", "10.00")]))
        created = self.client.post(reverse("hr:payroll_create"), data)
        payroll = Payroll.objects.get()
        self.assertRedirects(created, reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertEqual(AllowanceLine.objects.count(), 2)
        self.assertEqual(DeductionLine.objects.count(), 2)
        self.assertEqual(payroll.allowance_total, Decimal("70.00"))
        self.assertEqual(payroll.deduction_line_total, Decimal("35.00"))
        detail = self.client.get(reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertContains(detail, "Phone")
        self.assertContains(detail, "Union")

    def test_empty_list_and_empty_report(self):
        self.client.force_login(self.payroll_user)
        listing = self.client.get(reverse("hr:payroll_list"))
        self.assertContains(listing, "No payroll runs yet.")
        self.assertContains(listing, "New payroll run")
        report = self.client.get(reverse("hr:payroll_report"), {
            "company": self.company.pk,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
        })
        self.assertContains(report, "No payroll runs for this period.")
        self.assertContains(report, "<dd>0</dd>")
        self.assertContains(report, "R0.00")

    def test_other_company_run_is_not_visible(self):
        other_company = Company.objects.create(
            company_name="Other Co",
            owner=self.outsider,
            phone="0100000001",
            address="9 Other Road",
            email="other@example.com",
        )
        hidden = Employee.objects.create(
            first_name="Hidden",
            last_name="Person",
            designation=self.designation,
            company=other_company,
            created_by=self.outsider,
            emp_code="HID009",
        )
        payroll = Payroll.objects.create(
            employee=hidden,
            rate=Decimal("100.00"),
            hours=Decimal("8.00"),
            income_tax=Decimal("10.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            created_by=self.outsider,
        )
        self.client.force_login(self.payroll_user)
        self.assertEqual(self.client.get(reverse("hr:payroll_detail", args=[payroll.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("hr:payroll_payslip", args=[payroll.pk])).status_code, 404)
        listing = self.client.get(reverse("hr:payroll_list"))
        self.assertNotContains(listing, "Hidden")
        report = self.client.get(reverse("hr:payroll_report"), {
            "company": other_company.pk,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        })
        self.assertContains(report, "Select a valid choice.")


def _tax_bands(rows, initial=0):
    total = len(rows) + 1
    data = {
        "bands-TOTAL_FORMS": str(total),
        "bands-INITIAL_FORMS": str(initial),
        "bands-MIN_NUM_FORMS": "0",
        "bands-MAX_NUM_FORMS": "1000",
    }
    for index, band in enumerate(rows):
        data[f"bands-{index}-id"] = band.get("id", "")
        data[f"bands-{index}-income_from"] = band["income_from"]
        data[f"bands-{index}-income_to"] = band.get("income_to", "")
        data[f"bands-{index}-rate_percent"] = band["rate_percent"]
        data[f"bands-{index}-base_tax"] = band.get("base_tax", "0.00")
        data[f"bands-{index}-above_amount"] = band.get("above_amount", "0.00")
        data[f"bands-{index}-DELETE"] = ""
    blank = len(rows)
    data[f"bands-{blank}-id"] = ""
    data[f"bands-{blank}-income_from"] = ""
    data[f"bands-{blank}-income_to"] = ""
    data[f"bands-{blank}-rate_percent"] = ""
    data[f"bands-{blank}-base_tax"] = ""
    data[f"bands-{blank}-above_amount"] = ""
    data[f"bands-{blank}-DELETE"] = ""
    return data


class PayeTableTests(HrFixture):
    def pay_run(self, remuneration, code, born=None, start=None):
        employee = Employee.objects.create(
            first_name="Paye",
            last_name="Band",
            designation=self.designation,
            company=self.company,
            created_by=self.payroll_user,
            emp_code=code,
            date_of_birth=born,
        )
        start = start or date(2026, 3, 1)
        payroll = Payroll.objects.create(
            employee=employee,
            rate=remuneration,
            hours=Decimal("1.00"),
            start_date=start,
            end_date=start,
            created_by=self.payroll_user,
        )
        payroll.refresh_from_db()
        return payroll

    def test_sars_2027_bands_and_age_rebates(self):
        year = TaxYear.objects.get(name="2026/27")
        self.assertEqual(year.start_date, date(2026, 3, 1))
        self.assertEqual(year.end_date, date(2027, 2, 28))
        self.assertEqual(
            annual_tax(Decimal("245101"), list(year.bands.all())),
            Decimal("44118.26"),
        )
        self.assertEqual(self.pay_run(Decimal("20425.00"), "PAYE01").income_tax, Decimal("2191.50"))
        self.assertEqual(self.pay_run(Decimal("30000.00"), "PAYE02").income_tax, Decimal("4681.00"))
        self.assertEqual(
            self.pay_run(Decimal("30000.00"), "PAYE03", born=date(1961, 2, 28)).income_tax,
            Decimal("3867.25"),
        )
        self.assertEqual(
            self.pay_run(Decimal("30000.00"), "PAYE04", born=date(1940, 1, 1)).income_tax,
            Decimal("3596.50"),
        )
        self.assertEqual(self.pay_run(Decimal("10000.03"), "PAYE05").income_tax, Decimal("315.01"))

        kept = Payroll.objects.create(
            employee=Employee.objects.get(emp_code="PAYE01"),
            rate=Decimal("100.00"),
            hours=Decimal("8.00"),
            income_tax=Decimal("10.00"),
            start_date=date(2025, 11, 17),
            created_by=self.payroll_user,
        )
        self.assertEqual(kept.income_tax, Decimal("10.00"))

    def test_payroll_officer_can_add_a_tax_year_and_hr_cannot(self):
        self.client.force_login(self.hr)
        denied = self.client.get(reverse("hr:tax_year_list"))
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "Payroll group", status_code=403)

        self.client.force_login(self.payroll_user)
        listing = self.client.get(reverse("hr:tax_year_list"))
        self.assertContains(listing, "2026/27")
        created = self.client.post(reverse("hr:tax_year_create"), {
            "name": "2027/28",
            "start_date": "2027-03-01",
            "end_date": "2028-02-29",
            "primary_rebate": "0.00",
            "secondary_rebate": "0.00",
            "tertiary_rebate": "0.00",
            **_tax_bands([
                {"income_from": "0.00", "income_to": "100000.00", "rate_percent": "18.00"},
                {
                    "income_from": "100001.00",
                    "income_to": "",
                    "rate_percent": "26.00",
                    "base_tax": "18000.00",
                    "above_amount": "100000.00",
                },
            ]),
        })
        self.assertRedirects(created, reverse("hr:tax_year_list"))
        year = TaxYear.objects.get(name="2027/28")
        self.assertEqual(year.end_date, date(2028, 2, 29))
        payroll = self.pay_run(Decimal("1000.00"), "PAYE06", start=date(2027, 3, 15))
        self.assertEqual(payroll.income_tax, Decimal("180.00"))

    def test_saving_a_year_recalculates_unpaid_runs_only(self):
        unpaid = self.pay_run(Decimal("10000.00"), "PAYE07")
        paid = self.pay_run(Decimal("10000.00"), "PAYE08")
        self.assertEqual(unpaid.income_tax, Decimal("315.00"))
        self.assertEqual(paid.income_tax, Decimal("315.00"))
        PayrollPayment.objects.create(
            payroll=paid,
            method="eft",
            payment_date=date(2026, 3, 31),
            reference="EFT-PAID",
            amount=paid.get_nett_salary,
            recorded_by=self.payroll_user,
        )
        year = TaxYear.objects.get(name="2026/27")
        bands = [
            {
                "id": band.pk,
                "income_from": band.income_from,
                "income_to": "" if band.income_to is None else band.income_to,
                "rate_percent": band.rate_percent,
                "base_tax": band.base_tax,
                "above_amount": band.above_amount,
            }
            for band in year.bands.all()
        ]
        self.client.force_login(self.payroll_user)
        saved = self.client.post(reverse("hr:tax_year_edit", args=[year.pk]), {
            "name": year.name,
            "start_date": "2026-03-01",
            "end_date": "2027-02-28",
            "primary_rebate": "19020.00",
            "secondary_rebate": year.secondary_rebate,
            "tertiary_rebate": year.tertiary_rebate,
            **_tax_bands(bands, initial=len(bands)),
        })
        self.assertRedirects(saved, reverse("hr:tax_year_list"))
        unpaid.refresh_from_db()
        paid.refresh_from_db()
        self.assertEqual(unpaid.income_tax, Decimal("215.00"))
        self.assertEqual(paid.income_tax, Decimal("315.00"))


class PackageSalaryTests(HrFixture):
    def test_a_permanent_contract_uses_the_monthly_package(self):
        _, employee = self.create_employee(
            email_address="permanent@example.com",
            emp_code="PRM001",
            employee_type="Contract",
            gross_salary="20000.00",
            hourly_rate="400.00",
        )
        Contract.objects.create(
            employee=employee,
            contract_type="permanent",
            start_date=date(2026, 3, 1),
            job_title="Advisor",
            notice_period_days=30,
            is_current=True,
        )
        self.assertEqual(employee.pay_basis(), "package")
        self.client.force_login(self.payroll_user)
        created = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "rate": "400.00",
            "hours": "10.00",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        payroll = Payroll.objects.get()
        self.assertRedirects(created, reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertIsNone(payroll.rate)
        self.assertEqual(payroll.basic_salary, Decimal("20000.00"))
    def test_gross_salary_is_the_package_until_the_employee_leaves(self):
        _, employee = self.create_employee(gross_salary="30000.00")
        employee.refresh_from_db()
        self.assertEqual(employee.gross_salary, Decimal("30000.00"))
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "R30000.00")

        self.client.force_login(self.payroll_user)
        form_page = self.client.get(reverse("hr:payroll_create"))
        self.assertContains(form_page, '"basis": "package"')
        self.assertContains(form_page, "30000.00")
        created = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "rate": "",
            "hours": "",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        payroll = Payroll.objects.get()
        self.assertRedirects(created, reverse("hr:payroll_detail", args=[payroll.pk]))
        payroll.refresh_from_db()
        self.assertIsNone(payroll.rate)
        self.assertEqual(payroll.basic_salary, Decimal("30000.00"))
        self.assertEqual(payroll.uif_contribution, Decimal("300.00"))
        self.assertEqual(payroll.income_tax, Decimal("4681.00"))
        self.assertEqual(payroll.get_nett_salary, Decimal("25019.00"))
        run_page = self.client.get(reverse("hr:payroll_detail", args=[payroll.pk]))
        self.assertContains(run_page, "Monthly gross")
        self.assertContains(run_page, "R4681.00")

        unpaid = Payroll.objects.create(
            employee=employee,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            created_by=self.payroll_user,
        )
        self.assertEqual(unpaid.basic_salary, Decimal("30000.00"))
        PayrollPayment.objects.create(
            payroll=payroll,
            method="eft",
            payment_date=date(2026, 3, 31),
            reference="EFT-GROSS",
            amount=payroll.get_nett_salary,
            recorded_by=self.payroll_user,
        )
        self.client.force_login(self.hr)
        updated = self.client.post(
            reverse("hr:employee_edit", args=[employee.pk]),
            self.employee_payload(gross_salary="20425.00"),
        )
        self.assertEqual(updated.status_code, 302)
        payroll.refresh_from_db()
        unpaid.refresh_from_db()
        self.assertEqual(payroll.basic_salary, Decimal("30000.00"))
        self.assertEqual(payroll.income_tax, Decimal("4681.00"))
        self.assertEqual(unpaid.basic_salary, Decimal("20425.00"))
        self.assertEqual(unpaid.uif_contribution, Decimal("204.25"))
        self.assertEqual(unpaid.income_tax, Decimal("2191.50"))

        self.client.post(
            reverse("hr:employee_edit", args=[employee.pk]),
            self.employee_payload(status="Retired", gross_salary="20425.00"),
        )
        unpaid.refresh_from_db()
        self.assertEqual(unpaid.basic_salary, Decimal("0.00"))
        self.client.force_login(self.payroll_user)
        refused = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "rate": "",
            "hours": "",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        self.assertContains(refused, "This employee has left or retired.")

    def test_a_run_needs_a_rate_when_the_employee_has_no_gross_salary(self):
        _, employee = self.create_employee(email_address="hourly@example.com", emp_code="HRL001")
        self.client.force_login(self.payroll_user)
        response = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "rate": "",
            "hours": "",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        self.assertContains(response, "Add a gross salary on the employee file before running payroll.")
        self.assertEqual(Payroll.objects.count(), 0)
        employee.employee_type = "Contract"
        employee.hourly_rate = Decimal("100.00")
        employee.save()
        missing_hours = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "gross_salary": "99999.00",
            "rate": "50.00",
            "hours": "",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        self.assertContains(missing_hours, "Enter the ordinary hours for this rate.")
        self.assertEqual(Payroll.objects.count(), 0)
        created = self.client.post(reverse("hr:payroll_create"), {
            "employee": employee.pk,
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "gross_salary": "99999.00",
            "rate": "50.00",
            "hours": "10.00",
            "overtime_hours": "0.00",
            "overtime_rate": "0.00",
            **_line_data("allowances", []),
            **_line_data("deductions", []),
        })
        payroll = Payroll.objects.get()
        self.assertRedirects(created, reverse("hr:payroll_detail", args=[payroll.pk]))
        employee.refresh_from_db()
        self.assertIsNone(employee.gross_salary)
        self.assertEqual(payroll.rate, Decimal("100.00"))
        self.assertEqual(payroll.basic_salary, Decimal("1000.00"))
