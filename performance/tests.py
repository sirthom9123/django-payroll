from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from employee.models import Employee
from employee.tests import HrFixture
from performance.models import (
    Agreement,
    AgreementStatus,
    Appraisal,
    AppraisalScore,
    DevelopmentPlan,
    ImprovementPlan,
    KeyPerformanceArea,
    KeyPerformanceIndicator,
    SkillAssessment,
)


class PerformanceFixture(HrFixture):
    def setUp(self):
        super().setUp()
        self.manager_group = Group.objects.get(name="Manager")
        self.manager = User.objects.create_user("manager.user", password=self.password, is_staff=True)
        self.manager.groups.add(self.manager_group)

    def add_agreement(self, employee, cycle="2026/27", status="draft"):
        self.client.force_login(self.hr)
        return self.client.post(reverse("hr:agreement_create"), {
            "employee": employee.pk,
            "cycle": cycle,
            "status": status,
        })

    def add_area(self, agreement, name="Client work"):
        self.client.force_login(self.hr)
        return self.client.post(reverse("hr:kpa_create", args=[agreement.pk]), {"name": name})

    def add_indicator(self, area, name, weight):
        self.client.force_login(self.hr)
        return self.client.post(reverse("hr:kpi_create", args=[area.pk]), {
            "name": name,
            "measure": f"How {name} is judged",
            "weight": str(weight),
        })


class PerformanceAccessTests(PerformanceFixture):
    def test_a_new_agreement_is_saved_as_a_draft(self):
        self.client.force_login(self.hr)
        page = self.client.get(reverse("hr:agreement_create"))
        self.assertContains(page, "Save this as a draft.")
        self.assertContains(page, "add the indicators")
        self.assertNotContains(page, 'value="active"')

    def test_logged_out_user_is_sent_to_sign_in(self):
        response = self.client.get(reverse("hr:agreement_list"))
        self.assertRedirects(response, "/accounts/login/?next=/hr/performance/")

    def test_non_staff_user_cannot_open_performance(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("hr:agreement_list"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "You do not have access to HR.", status_code=403)

    def test_empty_lists(self):
        self.client.force_login(self.hr)
        agreements = self.client.get(reverse("hr:agreement_list"))
        self.assertContains(agreements, "No performance agreements yet.")
        self.assertContains(agreements, "New agreement")
        plans = self.client.get(reverse("hr:plan_list"))
        self.assertContains(plans, "No performance improvement plans yet.")
        self.assertContains(plans, "Add plan")
        skills = self.client.get(reverse("hr:skill_list"))
        self.assertContains(skills, "No skills assessments yet.")
        self.assertContains(skills, "Add assessment")
        development = self.client.get(reverse("hr:development_list"))
        self.assertContains(development, "No development plans yet.")
        self.assertContains(development, "Add development plan")

    def test_payroll_can_view_and_cannot_file(self):
        _, employee = self.create_employee()
        created = self.add_agreement(employee)
        agreement = Agreement.objects.get()
        self.assertRedirects(created, reverse("hr:agreement_detail", args=[agreement.pk]))
        self.client.force_login(self.payroll_user)
        listing = self.client.get(reverse("hr:agreement_list"))
        self.assertContains(listing, "Thabo Mokoena")
        self.assertNotContains(listing, "New agreement")
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "2026/27")
        self.assertNotContains(detail, "New agreement")
        denied = self.client.post(reverse("hr:agreement_create"), {
            "employee": employee.pk,
            "cycle": "2027/28",
            "status": "draft",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertContains(
            denied,
            "You can view performance records. Only HR or a manager can file them.",
            status_code=403,
        )
        self.assertEqual(Agreement.objects.count(), 1)
        for url in (
            reverse("hr:plan_create"),
            reverse("hr:skill_create"),
            reverse("hr:development_create"),
        ):
            blocked = self.client.get(url)
            self.assertEqual(blocked.status_code, 403)

    def test_manager_can_file_and_another_company_is_hidden(self):
        _, employee = self.create_employee()
        self.client.force_login(self.manager)
        opened = self.client.get(reverse("hr:agreement_create"))
        self.assertEqual(opened.status_code, 200)
        saved = self.client.post(reverse("hr:plan_create"), {
            "employee": employee.pk,
            "start_date": "2026-11-01",
            "review_date": "2026-12-01",
            "concern": "Late reports",
            "actions": "Weekly check-in",
            "outcome": "open",
            "outcome_note": "",
        })
        self.assertRedirects(saved, reverse("hr:plan_list"))
        self.assertEqual(ImprovementPlan.objects.get().filed_by, self.manager)

        other = Company.objects.create(
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
            company=other,
            created_by=self.outsider,
            emp_code="HID009",
        )
        secret = Agreement.objects.create(employee=hidden, cycle="2026/27", status=AgreementStatus.DRAFT)
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:agreement_detail", args=[secret.pk]))
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(reverse("hr:agreement_list"))
        self.assertNotContains(listing, "Hidden")

    def test_agreement_admin_lists_the_cycle(self):
        _, employee = self.create_employee()
        self.add_agreement(employee)
        admin = User.objects.create_superuser("admin.user", "admin@example.com", self.password)
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:performance_agreement_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026/27")


class PerformanceRecordTests(PerformanceFixture):
    def test_agreement_indicators_and_weighted_appraisal(self):
        _, employee = self.create_employee()
        self.add_agreement(employee)
        agreement = Agreement.objects.get()
        self.assertEqual(agreement.status, AgreementStatus.DRAFT)
        self.assertEqual(agreement.filed_by, self.hr)
        self.add_area(agreement)
        area = KeyPerformanceArea.objects.get()
        self.add_indicator(area, "Files closed", 60)
        self.add_indicator(area, "Call-backs", 40)
        self.assertEqual(agreement.weight_total(), 100)

        too_soon = self.client.post(reverse("hr:appraisal_form", args=[agreement.pk]), {}, follow=True)
        self.assertContains(too_soon, "File the appraisal only when the agreement is active.")
        self.assertEqual(too_soon.request["PATH_INFO"], f"/hr/performance/{agreement.pk}/")

        activated = self.client.post(reverse("hr:agreement_edit", args=[agreement.pk]), {
            "employee": employee.pk,
            "cycle": "2026/27",
            "status": "active",
        })
        self.assertRedirects(activated, reverse("hr:agreement_detail", args=[agreement.pk]))
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, AgreementStatus.ACTIVE)
        locked = self.client.get(reverse("hr:kpi_create", args=[area.pk]))
        self.assertRedirects(locked, reverse("hr:agreement_detail", args=[agreement.pk]))

        indicators = list(KeyPerformanceIndicator.objects.order_by("id"))
        today = timezone.localdate()
        filed = self.client.post(reverse("hr:appraisal_form", args=[agreement.pk]), {
            "appraisal_date": today.isoformat(),
            "overall_comment": "Steady year.",
            f"score_{indicators[0].pk}": "4",
            f"comment_{indicators[0].pk}": "On target",
            f"score_{indicators[1].pk}": "2",
            f"comment_{indicators[1].pk}": "",
        })
        self.assertRedirects(filed, reverse("hr:agreement_detail", args=[agreement.pk]))
        appraisal = Appraisal.objects.get()
        self.assertEqual(appraisal.overall_score(), Decimal("3.20"))
        self.assertEqual(appraisal.filed_by, self.hr)
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "3.20 out of 5")
        self.assertContains(detail, "Active")
        listing = self.client.get(reverse("hr:agreement_list"))
        self.assertContains(listing, "3.20 out of 5")

        back = self.client.post(reverse("hr:agreement_edit", args=[agreement.pk]), {"status": "draft"})
        self.assertContains(back, "This agreement has an appraisal. It cannot go back to draft.")
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, AgreementStatus.ACTIVE)

        closed = self.client.post(reverse("hr:agreement_edit", args=[agreement.pk]), {"status": "closed"})
        self.assertRedirects(closed, reverse("hr:agreement_detail", args=[agreement.pk]))
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, AgreementStatus.CLOSED)
        reopen = self.client.get(reverse("hr:agreement_edit", args=[agreement.pk]))
        self.assertRedirects(reopen, reverse("hr:agreement_detail", args=[agreement.pk]))

    def test_weights_cycle_and_dates_are_checked(self):
        _, employee = self.create_employee()
        bad_cycle = self.add_agreement(employee, cycle="2026/28")
        self.assertContains(bad_cycle, "Enter the cycle as 2026/27.")
        self.assertEqual(Agreement.objects.count(), 0)

        self.add_agreement(employee)
        agreement = Agreement.objects.get()
        again = self.add_agreement(employee, cycle="2026/27")
        self.assertContains(again, "This employee already has an agreement for this cycle.")
        self.assertEqual(Agreement.objects.count(), 1)

        self.add_area(agreement)
        area = KeyPerformanceArea.objects.get()
        self.add_indicator(area, "Files closed", 60)
        over = self.add_indicator(area, "Call-backs", 50)
        self.assertContains(over, "KPI weights cannot add to more than 100. They add to 110.")
        self.assertEqual(KeyPerformanceIndicator.objects.count(), 1)
        early = self.client.post(reverse("hr:agreement_edit", args=[agreement.pk]), {
            "employee": employee.pk,
            "cycle": "2026/27",
            "status": "active",
        })
        self.assertContains(early, "KPI weights must add to 100 before the agreement is active.")
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, AgreementStatus.DRAFT)

        low = self.add_indicator(area, "Call-backs", 0)
        self.assertContains(low, "Enter a weight from 1 to 100.")

        today = timezone.localdate()
        self.add_indicator(area, "Call-backs", 40)
        self.client.post(reverse("hr:agreement_edit", args=[agreement.pk]), {
            "employee": employee.pk,
            "cycle": "2026/27",
            "status": "active",
        })
        indicators = list(KeyPerformanceIndicator.objects.order_by("id"))
        future = self.client.post(reverse("hr:appraisal_form", args=[agreement.pk]), {
            "appraisal_date": (today + timedelta(days=1)).isoformat(),
            "overall_comment": "Too soon.",
            f"score_{indicators[0].pk}": "6",
            f"comment_{indicators[0].pk}": "",
            f"score_{indicators[1].pk}": "3",
            f"comment_{indicators[1].pk}": "",
        })
        self.assertContains(future, "The appraisal date cannot be in the future.")
        self.assertContains(future, "Enter a score from 1 to 5.")
        self.assertEqual(Appraisal.objects.count(), 0)

        backwards = self.client.post(reverse("hr:plan_create"), {
            "employee": employee.pk,
            "start_date": "2026-12-01",
            "review_date": "2026-11-01",
            "concern": "Late reports",
            "actions": "Weekly check-in",
            "outcome": "open",
            "outcome_note": "",
        })
        self.assertContains(backwards, "The review date must be on or after the start date.")
        self.assertEqual(
            backwards.content.decode().count("The review date must be on or after the start date."),
            1,
        )
        self.assertEqual(ImprovementPlan.objects.count(), 0)

        ahead = self.client.post(reverse("hr:skill_create"), {
            "employee": employee.pk,
            "skill": "Excel",
            "level": "9",
            "assessed_on": (today + timedelta(days=1)).isoformat(),
        })
        self.assertContains(ahead, "Enter a level from 1 to 5.")
        self.assertEqual(ahead.content.decode().count("Enter a level from 1 to 5."), 1)
        self.assertContains(ahead, "The assessment date cannot be in the future.")
        self.assertEqual(SkillAssessment.objects.count(), 0)

        self.client.post(reverse("hr:skill_create"), {
            "employee": employee.pk,
            "skill": "Excel",
            "level": "4",
            "assessed_on": (today - timedelta(days=1)).isoformat(),
        })
        self.client.post(reverse("hr:skill_create"), {
            "employee": employee.pk,
            "skill": "excel",
            "level": "2",
            "assessed_on": today.isoformat(),
        })
        self.client.post(reverse("hr:development_create"), {
            "employee": employee.pk,
            "skill_gap": "Report writing",
            "action": "Short course",
            "due_date": "2027-03-31",
            "status": "planned",
        })
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "excel")
        self.assertContains(detail, ">2<")
        self.assertNotContains(detail, ">4<")
        self.assertContains(detail, "Report writing")
        self.assertContains(detail, "Planned")
        self.assertEqual(DevelopmentPlan.objects.get().filed_by, self.hr)
        skills = self.client.get(reverse("hr:skill_list"))
        self.assertContains(skills, "Excel")
        self.assertContains(skills, "excel")


class PerformanceScoreTests(TestCase):
    def test_overall_score_needs_weights_that_add_to_100(self):
        from company.models import Company
        from employee.models import Department, Designation

        user = User.objects.create_user("score.user", password="test-pass-123", is_staff=True)
        department = Department.objects.create(name="Operations")
        designation = Designation.objects.create(department=department, name="Clerk")
        company = Company.objects.create(
            company_name="Score Co",
            owner=user,
            phone="0100000000",
            address="1 Test Street",
            email="score@example.com",
        )
        employee = Employee.objects.create(
            first_name="Amahle",
            last_name="Dlamini",
            designation=designation,
            company=company,
            created_by=user,
            emp_code="SCR001",
        )
        agreement = Agreement.objects.create(employee=employee, cycle="2026/27", status=AgreementStatus.ACTIVE)
        area = KeyPerformanceArea.objects.create(agreement=agreement, name="Work")
        first = KeyPerformanceIndicator.objects.create(kpa=area, name="One", measure="Count", weight=60)
        appraisal = Appraisal.objects.create(
            agreement=agreement,
            appraisal_date=timezone.localdate(),
            overall_comment="Partial",
            filed_by=user,
        )
        AppraisalScore.objects.create(appraisal=appraisal, kpi=first, score=5)
        self.assertIsNone(appraisal.overall_score())
