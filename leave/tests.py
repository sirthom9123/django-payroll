from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from company.models import Company
from employee.models import Employee
from employee.tests import HrFixture
from leave.balance import (
    annual_leave_days,
    balances_for,
    entitlement,
    maternity_last_day,
    parental_last_day,
    qualifying_days,
    working_days,
)
from leave.holidays import easter_sunday, public_holidays
from leave.models import (
    AnnualAccrual,
    Attendance,
    AttendanceStatus,
    LeaveApplication,
    LeaveKind,
    LeaveStatus,
    LeaveType,
)


def first_monday(month=3):
    day = date(timezone.localdate().year, month, 1)
    while day.weekday() != 0:
        day += timedelta(days=1)
    return day


class LeaveGroupTests(HrFixture):
    def test_migration_creates_the_manager_group_and_company_leave_types(self):
        self.assertTrue(Group.objects.filter(name="Manager").exists())
        self.assertEqual(self.company.leave_types.count(), 7)
        annual = self.company.leave_types.get(kind=LeaveKind.ANNUAL)
        self.assertEqual(annual.name, "Annual leave")
        self.assertEqual(annual.days_per_year, Decimal("15.00"))
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.SICK).days_per_year, Decimal("30.00"))
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.FAMILY).days_per_year, Decimal("3.00"))
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.STUDY).name, "Study leave")
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.PARENTAL).name, "Parental leave")
        self.assertEqual(annual.accrual, "cycle")
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.STUDY).days_per_year, Decimal("0.00"))
        self.assertEqual(self.company.leave_types.get(kind=LeaveKind.UNPAID).days_per_year, Decimal("0.00"))


class LeaveFixture(HrFixture):
    def setUp(self):
        super().setUp()
        self.manager_group = Group.objects.get(name="Manager")
        self.manager = User.objects.create_user("manager.user", password=self.password, is_staff=True)
        self.manager.groups.add(self.manager_group)
        self.monday = first_monday()
        self.friday = self.monday + timedelta(days=4)
        self.annual = self.company.leave_types.get(kind=LeaveKind.ANNUAL)
        self.annual.days_per_year = Decimal("15.00")
        self.annual.save()
        self.unpaid = self.company.leave_types.get(kind=LeaveKind.UNPAID)

    def leave_payload(self, employee, **overrides):
        data = {
            "employee": employee.pk,
            "leave_type": self.annual.pk,
            "start_date": self.monday.isoformat(),
            "end_date": self.friday.isoformat(),
            "reason": "Family visit",
            "action": "submit",
        }
        data.update(overrides)
        return data

    def submit(self, employee, **overrides):
        self.client.force_login(self.hr)
        return self.client.post(reverse("hr:leave_create"), self.leave_payload(employee, **overrides))


class LeaveAccessTests(LeaveFixture):
    def test_logged_out_user_is_sent_to_sign_in(self):
        response = self.client.get(reverse("hr:leave_list"))
        self.assertRedirects(response, "/accounts/login/?next=/hr/leave/")

    def test_non_staff_user_cannot_open_leave(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("hr:leave_list"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "You do not have access to HR.", status_code=403)

    def test_empty_leave_list_and_queue(self):
        self.client.force_login(self.hr)
        listing = self.client.get(reverse("hr:leave_list"))
        self.assertContains(listing, "No leave applications yet.")
        self.assertContains(listing, "Capture leave")
        self.client.force_login(self.manager)
        queue = self.client.get(reverse("hr:leave_approvals"))
        self.assertContains(queue, "No leave is waiting for a decision.")

    def test_payroll_can_view_leave_but_cannot_capture_it(self):
        _, employee = self.create_employee()
        self.client.force_login(self.payroll_user)
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "Annual leave")
        self.assertNotContains(detail, "Capture leave")
        denied = self.client.post(reverse("hr:leave_create"), self.leave_payload(employee))
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "Only HR can change it.", status_code=403)
        self.assertEqual(LeaveApplication.objects.count(), 0)

    def test_hr_cannot_approve_and_a_manager_cannot_capture(self):
        _, employee = self.create_employee()
        self.submit(employee)
        application = LeaveApplication.objects.get()
        self.client.force_login(self.hr)
        denied = self.client.post(reverse("hr:leave_decide", args=[application.pk]), {"action": "approve"})
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "Only a manager can approve or decline leave.", status_code=403)
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.SUBMITTED)
        self.client.force_login(self.manager)
        capture = self.client.get(reverse("hr:leave_create"))
        self.assertEqual(capture.status_code, 403)

    def test_another_company_leave_is_not_visible(self):
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
        application = LeaveApplication.objects.create(
            employee=hidden,
            leave_type=other.leave_types.get(kind=LeaveKind.ANNUAL),
            start_date=self.monday,
            end_date=self.friday,
            days=Decimal("5.00"),
            reason="Away",
            status=LeaveStatus.SUBMITTED,
        )
        self.client.force_login(self.hr)
        response = self.client.get(reverse("hr:leave_detail", args=[application.pk]))
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(reverse("hr:leave_list"))
        self.assertNotContains(listing, "Hidden")


class LeaveApplicationTests(LeaveFixture):
    def test_working_days_skip_the_weekend(self):
        self.assertEqual(self.monday.weekday(), 0)
        self.assertEqual(working_days(self.monday, self.friday), Decimal("5.00"))
        self.assertEqual(working_days(self.friday, self.monday + timedelta(days=7)), Decimal("2.00"))
        weekend = working_days(self.monday + timedelta(days=5), self.monday + timedelta(days=6))
        self.assertEqual(weekend, Decimal("0.00"))

    def test_hr_submits_leave_and_the_manager_approves_it(self):
        _, employee = self.create_employee()
        created = self.submit(employee)
        application = LeaveApplication.objects.get()
        self.assertRedirects(created, reverse("hr:leave_detail", args=[application.pk]))
        self.assertEqual(application.status, LeaveStatus.SUBMITTED)
        self.assertEqual(application.days, Decimal("5.00"))
        self.assertEqual(application.captured_by, self.hr)
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "Annual leave")
        self.assertContains(detail, "5.00")
        self.assertContains(detail, "Accumulates over the leave cycle")
        home = self.client.get(reverse("hr:home"))
        self.assertEqual(home.context["open_leave"], 1)

        self.client.force_login(self.manager)
        queue = self.client.get(reverse("hr:leave_approvals"))
        self.assertContains(queue, "Thabo Mokoena")
        decision = self.client.post(reverse("hr:leave_decide", args=[application.pk]), {
            "action": "approve",
            "decision_note": "",
        }, follow=True)
        self.assertContains(decision, "Leave approved.")
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.APPROVED)
        self.assertEqual(application.decided_by, self.manager)
        row = next(item for item in balances_for(employee, self.monday) if item["leave_type"].pk == self.annual.pk)
        self.assertEqual(row["taken"], Decimal("5.00"))
        self.assertEqual(row["pending"], Decimal("0.00"))
        self.assertEqual(row["remaining"], row["entitled"] - Decimal("5.00"))

    def test_decline_requires_a_note(self):
        _, employee = self.create_employee()
        self.submit(employee)
        application = LeaveApplication.objects.get()
        self.client.force_login(self.manager)
        missing = self.client.post(reverse("hr:leave_decide", args=[application.pk]), {
            "action": "decline",
            "decision_note": "  ",
        })
        self.assertContains(missing, "Enter a note to decline this leave.")
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.SUBMITTED)
        declined = self.client.post(reverse("hr:leave_decide", args=[application.pk]), {
            "action": "decline",
            "decision_note": "The week is already covered.",
        }, follow=True)
        self.assertContains(declined, "Leave declined.")
        self.assertContains(declined, "The week is already covered.")
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.DECLINED)
        row = next(item for item in balances_for(employee, self.monday) if item["leave_type"].pk == self.annual.pk)
        self.assertEqual(row["taken"], Decimal("0.00"))
        self.assertEqual(row["remaining"], row["entitled"])

    def test_validation_for_dates_overlap_and_balance(self):
        _, employee = self.create_employee()
        self.client.force_login(self.hr)
        backwards = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date=self.friday.isoformat(),
            end_date=self.monday.isoformat(),
        ))
        self.assertContains(backwards, "End date must be on or after the start date.")
        weekend = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date=(self.monday + timedelta(days=5)).isoformat(),
            end_date=(self.monday + timedelta(days=6)).isoformat(),
        ))
        self.assertContains(weekend, "These dates do not include a working day.")
        self.assertEqual(LeaveApplication.objects.count(), 0)

        self.annual.days_per_year = Decimal("1.00")
        self.annual.save()
        short = self.client.post(reverse("hr:leave_create"), self.leave_payload(employee))
        self.assertContains(short, "You do not have enough leave for these dates.")
        self.assertEqual(LeaveApplication.objects.count(), 0)

        self.annual.days_per_year = Decimal("15.00")
        self.annual.save()
        self.submit(employee)
        overlap = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date=self.friday.isoformat(),
            end_date=self.friday.isoformat(),
            reason="Another day",
        ))
        self.assertContains(overlap, "These dates overlap leave already on your record.")
        self.assertEqual(LeaveApplication.objects.count(), 1)

    def test_a_draft_does_not_use_the_balance_and_unpaid_is_not_limited(self):
        _, employee = self.create_employee()
        self.client.force_login(self.hr)
        draft = self.client.post(reverse("hr:leave_create"), self.leave_payload(employee, action="draft"))
        application = LeaveApplication.objects.get()
        self.assertRedirects(draft, reverse("hr:leave_detail", args=[application.pk]))
        self.assertEqual(application.status, LeaveStatus.DRAFT)
        row = next(item for item in balances_for(employee, self.monday) if item["leave_type"].pk == self.annual.pk)
        self.assertEqual(row["pending"], Decimal("0.00"))
        self.assertEqual(row["remaining"], row["entitled"])

        unpaid = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=self.unpaid.pk,
            reason="Unpaid absence",
        ))
        unpaid_row = LeaveApplication.objects.get(leave_type=self.unpaid)
        self.assertRedirects(unpaid, reverse("hr:leave_detail", args=[unpaid_row.pk]))
        self.assertEqual(unpaid_row.status, LeaveStatus.SUBMITTED)
        detail = self.client.get(reverse("hr:employee_detail", args=[employee.pk]))
        self.assertContains(detail, "Not limited")

    def test_cancelling_approved_leave_restores_the_balance(self):
        _, employee = self.create_employee()
        self.submit(employee)
        application = LeaveApplication.objects.get()
        self.client.force_login(self.manager)
        self.client.post(reverse("hr:leave_decide", args=[application.pk]), {"action": "approve"})
        self.client.force_login(self.hr)
        cancelled = self.client.post(reverse("hr:leave_cancel", args=[application.pk]), follow=True)
        self.assertContains(cancelled, "Leave cancelled.")
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.CANCELLED)
        row = next(item for item in balances_for(employee, self.monday) if item["leave_type"].pk == self.annual.pk)
        self.assertEqual(row["taken"], Decimal("0.00"))
        self.assertEqual(row["remaining"], row["entitled"])

    def test_approval_fails_when_the_balance_was_reduced(self):
        _, employee = self.create_employee()
        self.submit(employee)
        application = LeaveApplication.objects.get()
        self.annual.days_per_year = Decimal("4.00")
        self.annual.save()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("hr:leave_decide", args=[application.pk]), {"action": "approve"})
        self.assertContains(response, "You do not have enough leave for these dates.")
        application.refresh_from_db()
        self.assertEqual(application.status, LeaveStatus.SUBMITTED)

    def test_leave_counts_in_the_cycle_that_contains_the_start_date(self):
        _, employee = self.create_employee()
        year = timezone.localdate().year
        start = date(year, 12, 31)
        while start.weekday() != 0:
            start -= timedelta(days=1)
        end = start + timedelta(days=7)
        self.client.force_login(self.hr)
        response = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            reason="Year end",
        ))
        application = LeaveApplication.objects.get()
        self.assertRedirects(response, reverse("hr:leave_detail", args=[application.pk]))
        self.assertGreater(application.days, 0)
        during = next(item for item in balances_for(employee, start) if item["leave_type"].pk == self.annual.pk)
        nxt = date(year + 1, 3, 1)
        following = next(item for item in balances_for(employee, nxt) if item["leave_type"].pk == self.annual.pk)
        self.assertEqual(during["pending"], application.days)
        self.assertEqual(following["pending"], Decimal("0.00"))

    def test_leave_type_admin_lists_the_company_settings(self):
        admin = User.objects.create_superuser("admin.user", "admin@example.com", self.password)
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:leave_leavetype_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual leave")
        self.assertContains(response, "Study leave")
        self.assertContains(response, "Unpaid leave")


class StatutoryLeaveTests(LeaveFixture):
    def _person(self, hired):
        return Employee.objects.create(
            first_name="Amahle",
            last_name="Dlamini",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code=f"H{hired.strftime('%y%m%d')}",
            date_hired=hired,
            days_per_week=5,
        )

    def test_annual_leave_starts_small_and_reaches_15_at_the_end_of_the_cycle(self):
        hired = date(2026, 3, 2)
        employee = self._person(hired)
        opening = entitlement(employee, self.annual, hired)[0]
        self.assertGreater(opening, 0)
        self.assertLess(opening, Decimal("1.00"))
        closing = entitlement(employee, self.annual, date(2027, 3, 1))[0]
        self.assertEqual(closing, Decimal("15.00"))

    def test_unused_annual_leave_carries_for_six_months(self):
        employee = self._person(date(2024, 3, 1))
        anniversary = entitlement(employee, self.annual, date(2026, 3, 1))[0]
        self.assertGreater(anniversary, Decimal("15.00"))
        self.assertLess(anniversary, Decimal("16.00"))
        after_forfeiture = entitlement(employee, self.annual, date(2026, 8, 29))[0]
        self.assertLess(after_forfeiture, Decimal("15.00"))
        self.assertGreater(after_forfeiture, Decimal("5.00"))

    def test_sick_family_maternity_and_study_follow_their_own_rules(self):
        hired = date(2026, 3, 2)
        employee = self._person(hired)
        sick = self.company.leave_types.get(kind=LeaveKind.SICK)
        family = self.company.leave_types.get(kind=LeaveKind.FAMILY)
        study = self.company.leave_types.get(kind=LeaveKind.STUDY)
        self.assertEqual(entitlement(employee, sick, hired)[0], days_one_weekday())
        twenty_six = hired + timedelta(days=35)
        self.assertEqual(working_days(hired, twenty_six), Decimal("26.00"))
        self.assertEqual(entitlement(employee, sick, twenty_six)[0], Decimal("1.00"))
        self.assertEqual(entitlement(employee, sick, date(2026, 9, 2))[0], Decimal("30.00"))
        self.assertEqual(entitlement(employee, family, date(2026, 7, 2))[0], Decimal("0.00"))
        self.assertEqual(entitlement(employee, family, date(2026, 7, 3))[0], Decimal("3.00"))
        self.assertEqual(entitlement(employee, study, date(2027, 3, 1))[0], Decimal("0.00"))
        study.days_per_year = Decimal("10.00")
        study.save()
        self.assertLess(entitlement(employee, study, hired)[0], Decimal("1.00"))
        self.assertEqual(entitlement(employee, study, date(2027, 3, 1))[0], Decimal("10.00"))

        self.client.force_login(self.hr)
        early_family = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=family.pk,
            start_date="2026-06-01",
            end_date="2026-06-01",
            reason="Child is ill",
        ))
        self.assertContains(early_family, "Family responsibility leave is available after 4 months of employment.")
        within = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=self.company.leave_types.get(kind=LeaveKind.MATERNITY).pk,
            start_date="2026-03-02",
            end_date=maternity_last_day(date(2026, 3, 2)).isoformat(),
            reason="Maternity",
        ))
        self.assertEqual(within.status_code, 302)
        too_long = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=self.company.leave_types.get(kind=LeaveKind.MATERNITY).pk,
            start_date="2026-08-03",
            end_date=(maternity_last_day(date(2026, 8, 3)) + timedelta(days=1)).isoformat(),
            reason="Longer maternity",
        ))
        self.assertContains(too_long, "Maternity leave cannot be longer than 4 consecutive months.")


class PublicHolidayAndAgreementTests(LeaveFixture):
    def test_easter_and_a_sunday_public_holiday(self):
        self.assertEqual(easter_sunday(2023), date(2023, 4, 9))
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        self.assertIn(date(2023, 1, 1), public_holidays(2023))
        self.assertIn(date(2023, 1, 2), public_holidays(2023))
        goodwill = public_holidays(2022)
        self.assertIn(date(2022, 12, 25), goodwill)
        self.assertIn(date(2022, 12, 26), goodwill)
        self.assertNotIn(date(2022, 12, 27), goodwill)

    def test_a_weekday_public_holiday_is_not_deducted_from_annual_leave(self):
        _, employee = self.create_employee()
        start = date(2025, 12, 29)
        end = date(2026, 1, 2)
        self.assertEqual(working_days(start, end), Decimal("5.00"))
        self.assertEqual(annual_leave_days(start, end, employee), Decimal("4.00"))
        self.client.force_login(self.hr)
        holiday_only = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date="2023-01-02",
            end_date="2023-01-02",
            reason="New Year Monday",
        ))
        self.assertContains(holiday_only, "This public holiday is not deducted from annual leave.")
        employee.days_per_week = 3
        employee.save()
        self.assertEqual(annual_leave_days(start, end, employee), Decimal("5.00"))

    def test_one_day_for_every_17_days_worked_or_paid(self):
        hired = date(2026, 3, 2)
        employee = Employee.objects.create(
            first_name="Lerato",
            last_name="Ndlovu",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="P17",
            date_hired=hired,
            days_per_week=5,
        )
        end = hired + timedelta(days=22)
        self.annual.accrual = AnnualAccrual.PER_17
        self.annual.save()
        self.assertEqual(working_days(hired, end), Decimal("17.00"))
        self.assertEqual(qualifying_days(employee, hired, end), Decimal("17.00"))
        self.assertEqual(entitlement(employee, self.annual, hired)[0], Decimal("0.06"))
        self.assertEqual(entitlement(employee, self.annual, end)[0], Decimal("1.00"))
        employee.days_per_week = 4
        employee.save()
        self.assertEqual(qualifying_days(employee, hired, end), Decimal("13.60"))
        self.assertEqual(entitlement(employee, self.annual, end)[0], Decimal("0.80"))
        employee.days_per_week = 5
        employee.save()
        Attendance.objects.create(
            employee=employee,
            date=hired,
            status=AttendanceStatus.ABSENT,
            hours_worked=Decimal("0.00"),
            recorded_by=self.hr,
        )
        self.assertEqual(qualifying_days(employee, hired, end), Decimal("16.00"))
        self.assertEqual(entitlement(employee, self.annual, end)[0], Decimal("0.94"))

    def test_family_responsibility_needs_four_days_a_week(self):
        employee = Employee.objects.create(
            first_name="Sipho",
            last_name="Khumalo",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="FAM4",
            date_hired=date(2025, 1, 6),
            days_per_week=3,
        )
        family = self.company.leave_types.get(kind=LeaveKind.FAMILY)
        self.assertEqual(entitlement(employee, family, date(2026, 6, 1))[0], Decimal("0.00"))
        self.client.force_login(self.hr)
        short_week = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=family.pk,
            start_date="2026-06-01",
            end_date="2026-06-01",
            reason="Child is ill",
        ))
        self.assertContains(short_week, "Family responsibility leave is for an employee who works at least 4 days a week.")
        employee.days_per_week = None
        employee.save()
        missing = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=family.pk,
            start_date="2026-06-02",
            end_date="2026-06-02",
            reason="Child is ill",
        ))
        self.assertContains(missing, "Enter how many days a week this employee works before capturing family responsibility leave.")

    def test_parental_leave_follows_the_interim_sharing_rule(self):
        employee = Employee.objects.create(
            first_name="Naledi",
            last_name="Molefe",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="PAR1",
            date_hired=date(2024, 3, 1),
            days_per_week=5,
        )
        parental = self.company.leave_types.get(kind=LeaveKind.PARENTAL)
        start = date(2026, 3, 2)
        self.client.force_login(self.hr)
        missing = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=parental.pk,
            start_date=start.isoformat(),
            end_date="2026-03-06",
            reason="Parental",
        ))
        self.assertContains(missing, "Say whether the other parent is also employed.")
        sole = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=parental.pk,
            start_date=start.isoformat(),
            end_date="2026-03-06",
            other_parent_employed="false",
            reason="Only employed parent",
        ))
        self.assertEqual(sole.status_code, 302)
        gap = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=parental.pk,
            start_date="2026-03-10",
            end_date="2026-03-12",
            other_parent_employed="false",
            reason="A second block",
        ))
        self.assertContains(gap, "Parental leave must be taken in one uninterrupted run of days.")

        other = Employee.objects.create(
            first_name="Karabo",
            last_name="Molefe",
            designation=self.designation,
            company=self.company,
            created_by=self.hr,
            emp_code="PAR2",
            date_hired=date(2024, 3, 1),
            days_per_week=5,
        )
        within = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            other,
            leave_type=parental.pk,
            start_date=start.isoformat(),
            end_date=parental_last_day(start, shared=False).isoformat(),
            other_parent_employed="false",
            reason="Four months",
        ))
        self.assertEqual(within.status_code, 302)
        too_long = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            other,
            leave_type=parental.pk,
            start_date="2028-03-01",
            end_date=(parental_last_day(date(2028, 3, 1), shared=False) + timedelta(days=1)).isoformat(),
            other_parent_employed="false",
            reason="Longer than four months",
        ))
        self.assertContains(too_long, "Parental leave for the only employed parent cannot be longer than 4 consecutive months.")
        shared = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            other,
            leave_type=parental.pk,
            start_date="2028-03-06",
            end_date=parental_last_day(date(2028, 3, 6), shared=True).isoformat(),
            other_parent_employed="true",
            reason="Shared parental leave",
        ))
        self.assertEqual(shared.status_code, 302)
        shared_over = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            other,
            leave_type=parental.pk,
            start_date="2030-01-07",
            end_date=(parental_last_day(date(2030, 1, 7), shared=True) + timedelta(days=1)).isoformat(),
            other_parent_employed="true",
            reason="Longer than the shared pool",
        ))
        self.assertContains(shared_over, "Parental leave cannot be longer than 4 months and 10 days.")


def days_one_weekday():
    return Decimal("0.04")


class LeaveProofTests(LeaveFixture):
    def test_leave_can_be_saved_without_proof(self):
        _, employee = self.create_employee()
        self.submit(employee)
        application = LeaveApplication.objects.get()
        self.assertFalse(application.proof)
        detail = self.client.get(reverse("hr:leave_detail", args=[application.pk]))
        self.assertContains(detail, "No proof attached.")
        missing = self.client.get(reverse("hr:leave_proof", args=[application.pk]))
        self.assertEqual(missing.status_code, 404)

    def test_staff_can_download_a_sick_note_and_others_cannot(self):
        _, employee = self.create_employee()
        sick = self.company.leave_types.get(kind=LeaveKind.SICK)
        sick.days_per_year = Decimal("15.00")
        sick.save()
        self.client.force_login(self.hr)
        note = SimpleUploadedFile("sick-note.txt", b"fit for work from Monday", content_type="text/plain")
        created = self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            leave_type=sick.pk,
            reason="Flu",
            proof=note,
        ))
        application = LeaveApplication.objects.get()
        self.assertRedirects(created, reverse("hr:leave_detail", args=[application.pk]))
        self.assertTrue(application.proof.name.endswith("sick-note.txt"))
        detail = self.client.get(reverse("hr:leave_detail", args=[application.pk]))
        self.assertContains(detail, "Download proof")
        download = self.client.get(reverse("hr:leave_proof", args=[application.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"fit for work from Monday")
        self.assertIn("attachment", download["Content-Disposition"])

        self.client.logout()
        anonymous = self.client.get(reverse("hr:leave_proof", args=[application.pk]))
        self.assertRedirects(anonymous, f"/accounts/login/?next=/hr/leave/{application.pk}/proof/")
        self.client.force_login(self.plain)
        denied = self.client.get(reverse("hr:leave_proof", args=[application.pk]))
        self.assertEqual(denied.status_code, 403)

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
            emp_code="HID011",
        )
        hidden_leave = LeaveApplication.objects.create(
            employee=hidden,
            leave_type=other.leave_types.get(kind=LeaveKind.SICK),
            start_date=self.monday,
            end_date=self.monday,
            days=Decimal("1.00"),
            reason="Flu",
            status=LeaveStatus.SUBMITTED,
        )
        hidden_leave.proof.save("private-note.txt", ContentFile(b"private"), save=True)
        self.client.force_login(self.hr)
        hidden_download = self.client.get(reverse("hr:leave_proof", args=[hidden_leave.pk]))
        self.assertEqual(hidden_download.status_code, 404)


class AttendanceTests(LeaveFixture):
    def test_empty_register_and_timesheet(self):
        self.client.force_login(self.hr)
        register = self.client.get(reverse("hr:attendance"))
        self.assertContains(register, "No employees yet.")
        self.assertContains(register, "Add employee")
        sheet = self.client.get(reverse("hr:timesheet"))
        self.assertContains(sheet, "No attendance for this week.")

    def test_non_staff_cannot_open_attendance(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("hr:attendance"))
        self.assertEqual(response.status_code, 403)

    def test_hr_saves_the_register_and_the_timesheet_counts_absenteeism(self):
        _, employee = self.create_employee()
        wednesday = self.monday + timedelta(days=2)
        tuesday = self.monday + timedelta(days=1)
        self.client.force_login(self.hr)
        self.client.post(reverse("hr:leave_create"), self.leave_payload(
            employee,
            start_date=wednesday.isoformat(),
            end_date=wednesday.isoformat(),
            reason="Clinic",
        ))
        application = LeaveApplication.objects.get()
        self.client.force_login(self.manager)
        self.client.post(reverse("hr:leave_decide", args=[application.pk]), {"action": "approve"})

        self.client.force_login(self.hr)
        saved = self.client.post(reverse("hr:attendance"), {
            "date": self.monday.isoformat(),
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-employee_id": str(employee.pk),
            "form-0-status": AttendanceStatus.PRESENT,
            "form-0-hours_worked": "8.00",
        })
        self.assertRedirects(saved, f"/hr/attendance/?date={self.monday.isoformat()}")
        self.client.post(reverse("hr:attendance"), self._register(employee, tuesday, AttendanceStatus.ABSENT, "0.00"))
        self.client.post(reverse("hr:attendance"), self._register(employee, wednesday, AttendanceStatus.ABSENT, "0.00"))

        sheet = self.client.get(reverse("hr:timesheet") + f"?week={wednesday.isoformat()}")
        self.assertContains(sheet, "Thabo Mokoena")
        self.assertContains(sheet, 'class="total">8.00<')
        self.assertContains(sheet, 'class="absent-count">1<')
        self.assertEqual(Attendance.objects.filter(employee=employee).count(), 3)

    def test_register_validation_and_a_hidden_employee(self):
        _, employee = self.create_employee()
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
            emp_code="HID010",
        )
        self.client.force_login(self.hr)
        too_long = self.client.post(
            reverse("hr:attendance"),
            self._register(employee, self.monday, AttendanceStatus.PRESENT, "24.01"),
        )
        self.assertContains(too_long, "Hours worked cannot be more than 24.")
        missing = self.client.post(
            reverse("hr:attendance"),
            self._register(employee, self.monday, "", "8.00"),
        )
        self.assertContains(missing, "Select a status.")
        tampered = self.client.post(
            reverse("hr:attendance"),
            self._register(hidden, self.monday, AttendanceStatus.PRESENT, "8.00"),
        )
        self.assertContains(tampered, "That employee is not on your list.")
        self.assertFalse(Attendance.objects.filter(employee=hidden).exists())
        self.client.force_login(self.payroll_user)
        denied = self.client.post(
            reverse("hr:attendance"),
            self._register(employee, self.monday, AttendanceStatus.PRESENT, "8.00"),
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def _register(self, employee, day, status, hours):
        return {
            "date": day.isoformat(),
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-employee_id": str(employee.pk),
            "form-0-status": status,
            "form-0-hours_worked": hours,
        }


class LeaveTypeAdminTests(TestCase):
    def test_models_are_registered(self):
        from django.contrib import admin

        self.assertIn(LeaveType, admin.site._registry)
        self.assertIn(LeaveApplication, admin.site._registry)
        self.assertIn(Attendance, admin.site._registry)
