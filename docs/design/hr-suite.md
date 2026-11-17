# HR suite — programme brief

**Status.** Phase 1 is built on `feat/hr-employee-records` (2026-11-17). It is not deployed. Phases 2–6 are still waiting for their own approval.
**Date.** 2026-11-17
**Users.** HR officers at a desk. Payroll officers for pay. Line managers later, for leave and appraisals. Employees, on their own sign-in, for their profile, leave, payslips, and IRP5.
**Build target.** Server-rendered Django templates for daily HR work, plus Django admin for setup. No separate frontend, no JSON API.
**Visuals.** Pending. Flows below are the spec until a mock is requested.

Point 5 in the request stopped at the heading “Recruitment, Talent and Skills Development”. The bullets under that heading are not in this brief. Phase 5 below is a placeholder so the programme can be ordered. Replace it when the rest of that list arrives.

## What exists today

| Area | Already in the app | Missing |
|---|---|---|
| Company | `company.Company` (name, owner, phones, address, email, logo) | No link from an employee to a company |
| People | `Employee`: names, ID number, passport, contact, address, designation, hire and departure dates, pension number, type, status, bank details | Contracts, job description, qualifications, employment history, documents |
| Org | `Department`, `Designation` | Job description is only a free-text field on designation |
| Pay | `Payroll`: rate × hours = basic salary, manual income tax, UIF at 1% of basic, shared benefit and deduction catalogues, payslip PDF | Overtime, per-payslip allowances, PAYE rules, payroll reports, payment records |
| Leave, attendance, performance, recruitment | None | Entire modules |
| Employee sign-in | None. Every custom view is staff-only | Own profile, leave applications, payslip PDFs, IRP5 |

Staff reach the app through Django admin. The only custom screen is the payslip PDF (`employee.views.admin_export_payroll_pdf`).

## How the HR UI should work

HR should not live only inside the stock admin changelists. Daily work gets its own pages under `/hr/`, still Django templates, still Django sessions.

- Every `/hr/` view requires a logged-in staff user (`staff_member_required` or the same check).
- Three groups, assigned in admin:
  - **HR** — employee records, documents, leave capture.
  - **Payroll** — salary runs, payslips, payment records, payroll reports.
  - **Manager** — approve leave, and later record appraisals for people they manage. Not in phase 1.
- A user with no group who is still staff sees a short “no access” page, not another employee’s file.
- Company and employee rows stay scoped the way `owner` and `created_by` already intend. A staff user must not open a record they are not allowed to see.
- Personal data (ID numbers, passports, bank details, documents, payslips, IRP5s) is shown to the staff role that needs it, and to the employee it belongs to. No public links. Fake names and ZAR amounts only in designs and tests.
- One primary action per screen. Labels on every input. Errors say what to fix. Amounts in ZAR with two decimals. Dates in Africa/Johannesburg.
- Empty lists say what is missing and which button creates the first row. A bad form redisplays the same page with field errors. A missing record is a 404. A user without the group gets the no-access page.

Proposed shell (built in phase 1, reused after that):

| Screen | Template | Who |
|---|---|---|
| Sign-in | Django’s login view, `templates/registration/login.html` | Staff |
| Home | `templates/hr/home.html` | HR or Payroll |
| No access | `templates/hr/no_access.html` | Staff with neither group |

Home shows counts only: active employees, payroll runs this month, and later open leave. It does not show ID numbers or bank details.

Employees use a second area, `/me/`. It is the same site and the same Django login. An employee account is a normal user linked to one `Employee` row. It is not staff, and it is not in the HR, Payroll, or Manager groups.

- `/me/` requires a signed-in user whose account is linked to an employee. It does not use `staff_member_required`.
- Every query is limited to that one employee. A payslip, leave row, or IRP5 for someone else returns 404.
- The employee can update phone, alternate phone, email, and home address. Name, ID or passport, job, pay, and bank details stay read-only.
- After sign-in, staff in HR or Payroll land on `/hr/`. A linked employee who is not staff lands on `/me/`.
- A staff user with no linked employee who opens `/me/` sees a short page: “This sign-in is not linked to an employee.”

| Screen | Template | Who |
|---|---|---|
| My home | `templates/me/home.html` | Linked employee |
| Not linked | `templates/me/not_linked.html` | Staff with no employee link |

## Phases

Build one phase per branch, after this file is approved for that phase. Do not start phase 2 maths until phase 1 records are in place, because payslips must point at a stable employee.

### Phase 1 — Employee records and HR administration

Extends `employee`. No change to payslip totals.

**Job.** An HR officer keeps a complete file for each person: who they are, what job they hold, what they are qualified for, where they worked before, and the documents on file.

**Screens**

1. **Employee list** — `templates/hr/employee_list.html`. Search by name or employee code. Filter by department, status, employment type. Columns: code, name, designation, department, status, date hired. Primary action: Add employee. Empty: “No employees yet.”
2. **Employee file** — `templates/hr/employee_detail.html`. Header: name, code, status, designation. Sections (each can be empty): Personal, Job, Contract, Qualifications, Employment history, Documents, Bank (masked account number, last four digits only). Primary action depends on the section the user opened.
3. **Add / edit personal and job** — `templates/hr/employee_form.html`. Same fields as `Employee` today, plus a required company. Validation copy: “Enter a 13-digit South African ID number, or a passport number.” One of ID number or passport is required. Email must be a valid address. Date departed cannot be before date hired.
4. **Contract** — `templates/hr/contract_form.html`. One current contract, older rows kept. Fields: contract type (permanent, fixed-term, intern), start, end (required for fixed-term), job title, job description, notice period, signed date. Primary action: Save contract.
5. **Qualification** — `templates/hr/qualification_form.html`. Institution, qualification name, year completed, NQF level (optional). A person can have several.
6. **Employment history** — `templates/hr/history_form.html`. Employer, role, start, end, reason for leaving. This is prior employment, separate from the current designation.
7. **Document** — `templates/hr/document_form.html`. Title, type (ID copy, contract, qualification, other), file, date added. HR can download. There is no anonymous download URL.

**Leave records** stay as a read-only section on the employee file until phase 3. In phase 1 the section says “Leave is not captured yet.”

**Acceptance.** An HR user can add a person, save a contract, add a qualification, add a history row, and upload a document. A Payroll-only user can open the file but cannot edit it. A logged-out user is sent to sign-in. Payslip PDF output is unchanged.

### Phase 2 — Payroll and remuneration

Stays in `employee`. This phase changes money. It needs its own approval after phase 1, plus tests for the happy path, a non-staff denial, and rounding.

**Do not change these rules until that approval:**

- Basic salary is `rate × hours`.
- UIF is 1% of basic salary (employee portion only, no earnings cap).
- Income tax is typed in. It is not calculated from SARS tables.
- Benefits and deductions are shared catalogues. The same row’s amount is reused wherever it is attached. That cannot represent a different allowance per employee.

**Job.** A payroll officer runs a month, records overtime and allowances on that run, keeps PAYE and UIF as explicit figures, downloads the payslip, files a payment, and prints a period report.

**Screens**

1. **Payroll list** — period, employee, gross, deductions, nett, paid or unpaid. Primary action: New payroll run.
2. **Payroll run** — employee, period start and end, rate, ordinary hours, overtime hours, overtime rate, income tax (PAYE), UIF, allowance lines, deduction lines, nett. Amounts are calculated in Python with `Decimal`, then shown. The officer saves; the page does not calculate in the browser.
3. **Payslip** — existing PDF, extended only when the run has overtime or lines. ZAR, two decimals.
4. **Payment record** — method (EFT or cash), payment date, reference, amount (must equal nett). One payment per run.
5. **Payroll report** — one period, one company: headcount, total gross, total PAYE, total UIF, total nett. HTML page first. PDF only if the HTML report is accepted.

**Still out of this phase unless you ask:** SARS tax tables, medical tax credits, SDL, employer UIF, and EMP201. Those need a written rule before any formula is coded. The current 1% UIF and manual PAYE stay until that rule exists. The IRP5 in phase 6 prints the PAYE and UIF already stored on the runs. It does not recalculate them.

### Phase 3 — Leave and attendance

New `leave` app. `employee` does not gain more payroll fields for this.

**Job.** An employee submits their own leave. HR can capture leave on someone’s behalf. A manager approves or declines it. Balances are visible on the employee file and, from phase 6, on `/me/`.

**Screens**

1. Leave types (admin): annual, sick, family responsibility, maternity, unpaid. Days per year are company settings, not hardcoded BCEA maths, until you confirm the policy.
2. Leave application: employee, type, start, end, reason. States: draft, submitted, approved, declined, cancelled.
3. Approval queue for Manager: approve or decline, with a note required on decline.
4. Balance on the employee file: entitled, taken, remaining. Remaining cannot go below zero unless the type allows unpaid leave.
5. Attendance register: date, employee, status (present, absent, leave, public holiday), hours worked.
6. Timesheet: week, daily hours, total. Absenteeism is a count of “absent” rows with no approved leave on that date.

No clock-in devices in this phase. HR captures the register.

### Phase 4 — Performance and development

New `performance` app.

**Job.** HR or a manager files the year’s agreement and the appraisal. Employees do not open performance records on `/me/`. Their sign-in covers profile, leave, payslips, and IRP5 only.

**Screens**

1. Performance agreement: employee, cycle (for example 2026/27), status.
2. KPA with one or more KPIs: name, measure, weight. Weights on one agreement must add to 100.
3. Appraisal: score per KPI, comment, overall comment, date.
4. Performance improvement plan: start, review date, concern, actions, outcome.
5. Skills assessment: skill, level (1–5), date.
6. Individual development plan: skill gap, action, due date, status.

### Phase 5 — Recruitment, talent and skills development

**Blocked on the rest of your list.** Placeholder only:

- Vacancy, application, and a hired-applicant handoff that creates an `Employee`.
- No public careers site until you ask for one.
- Skills development that overlaps phase 4 (assessments and development plans) stays in phase 4 so it is not built twice.

### Phase 6 — Employee portal and IRP5

Depends on phases 1, 2, and 3. New templates under `templates/me/`. The employee link can live on `Employee` (one user, one employee). IRP5 rows live with payroll.

**Job.** An employee signs in and sees only their own file. They apply for leave, download payslips, and download an IRP5 for a tax year. Payroll issues the IRP5. The employee cannot issue one.

**Tax year.** South African tax year, 1 March to the end of February. One IRP5 per employee per tax year.

**Screens**

1. **My home** — `templates/me/home.html`. Name, designation, leave remaining (once phase 3 exists), latest payslip, latest IRP5. Primary action: Apply for leave. Empty payslip and empty IRP5 each say so, with no button that invents a document.
2. **My profile** — `templates/me/profile.html`. Read-only: employee code, names, ID number or passport, designation, department, status, date hired, bank name and last four digits of the account. Editable: email, phone, alternate phone, address, city, postal code. Primary action: Save contact details. Job, pay, and bank edits are refused with “Ask HR to change this.”
3. **Apply for leave** — `templates/me/leave_form.html`. Type, start, end, reason. Primary action: Submit. The row is created as submitted, for this employee only. End date before start date: “End date must be on or after the start date.” Overlap with leave that is submitted or approved: “These dates overlap leave already on your record.” Remaining balance below the requested days, except unpaid: “You do not have enough leave for these dates.” The employee cannot approve their own application.
4. **My leave** — `templates/me/leave_list.html`. Own rows only: type, dates, status, and the manager’s note when declined. Empty: “You have no leave applications.”
5. **My payslips** — `templates/me/payslip_list.html`. Own payroll runs: period, nett salary, download. The download is the same payslip PDF payroll uses. Another employee’s payroll id returns 404. Empty: “No payslips yet.”
6. **Issue IRP5** — `templates/hr/irp5_form.html`. Payroll group only. Choose employee and tax year, then issue. Totals are the sum of that employee’s payroll runs in the tax year: remuneration, PAYE (`income_tax`), and employee UIF. Figures are `Decimal`, shown in ZAR with two decimals. Issuing again for the same employee and year replaces the current certificate. There is no SARS upload on this screen.
7. **My IRP5s** — `templates/me/irp5_list.html`. Own certificates: tax year and download. The PDF names the document IRP5 and shows employer, employee, tax year, remuneration, PAYE, and UIF for that year. Empty: “No IRP5 for this tax year yet.” Payroll can download the same PDF from the employee file.

**Acceptance.** A linked employee can update a phone number, submit leave, and download only their payslip and their IRP5. They cannot open another employee’s profile, leave, payslip, or IRP5. A logged-out user is sent to sign-in. A user who is not linked gets the not-linked page. Payslip totals are unchanged by the download. The IRP5 equals the sum of the stored runs for that tax year.

**Not in this phase.** SARS eFiling, e@syFile, EMP201, medical tax credits, and a change to how PAYE is calculated.

## Decisions needed before phase 1 code

1. Phase 1 is the slice that was built. Phases 2–6 still need their own approval.
2. Confirm HR and Payroll as the two groups for the first release.
3. Send the missing bullets for recruitment when you have them.
4. Leave the payslip formula as it is until a separate payroll approval.
5. Phase 6 (employee portal and IRP5) waits until phases 1, 2, and 3 are in place.

## Out of scope for the whole programme until you add it

- A mobile app.
- Biometric clocks.
- SARS eFiling, e@syFile, EMP201, and medical aid tax credits.
- Email to real employees.
- Employees editing job, pay, or bank details.
- Employees opening performance, recruitment, or other people’s records.
- Anything other than Django templates, Django admin, MySQL, and cPanel.
