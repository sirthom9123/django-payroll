import os
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from employee.models import (
    BankInfo,
    Contract,
    Department,
    Designation,
    Employee,
    EmployeeDocument,
    EmploymentHistory,
    Payroll,
    Qualification,
    Status,
    hr_document_storage,
)


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
        self.assertContains(detail, "Leave is not captured yet.")

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
        self.assertContains(response, "Leave is not captured yet.")

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
        stored_uif = (rate * hours * Decimal(0.01)).quantize(Decimal("0.01"))
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
