# Decisions

## 2026-11-17 — Django templates on cPanel

**Decision.** Payroll stays a Django project: Django admin and Django templates, MySQL, deployed on cPanel (Passenger / WSGI). No Next.js, React, Django REST Framework, FastAPI, Railway, or Vercel.

**Why.** The app is already Django (`app`, `company`, `employee`) with one payslip template and a MySQL database. The agent rules copied into this folder described Smart Minds (Next.js + Railway) and were sending work toward the wrong stack.

**Consequence.** `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/payroll.mdc`, and the local `yehuda-*` skills are Payroll overrides. Do not regenerate them with `scripts/dev_sync_rules.py --write`.

## 2026-11-17 — Employee portal and IRP5

**Decision.** Employees get their own sign-in, linked to one employee record, under `/me/`. They can view their profile, edit contact details, apply for leave, and download their own payslips and IRP5s. The tax certificate is an IRP5 for the South African tax year (1 March to end of February). It sums PAYE, UIF, and remuneration already stored on payroll runs. It does not recalculate PAYE and it is not filed with SARS from this app.

**Why.** Tshiamo confirmed the HR programme must include employee access, and that the tax certificate is an IRP5.

**Consequence.** Phase 6 in `docs/design/hr-suite.md`. Employee accounts are not staff. Portal queries are limited to the signed-in employee. eFiling, e@syFile, and EMP201 stay out of scope.

## 2026-11-17 — Phase 1 HR records

**Decision.** Employee files live under `/hr/` in the `employee` app. Two Django groups, `HR` and `Payroll`, are created by migration `0009_hr_employee_records`. HR can change the file. Payroll can open it and download documents. Staff in neither group see the no-access page. A logged-out user is sent to `/accounts/login/`.

An employee is visible when the user is a superuser, owns the company, created the row, the company is still unset, or the company owner is in HR or Payroll. `Employee.company` is nullable in the database so existing rows can migrate, and the HR form requires a company. Documents are stored in `hr_documents/` through `HrDocumentStorage`, with a staff download view. Payslip maths is unchanged.

`python manage.py test` uses an in-memory SQLite database. `runserver` and `migrate` still use MySQL. If `mysqlclient` is not installed, settings fall back to PyMySQL. PyMySQL is not a project requirement.

**Why.** Phase 1 was started from the approved brief. Payroll officers have to open files they did not create. Existing employees have no company yet. This machine could not log in to MySQL, so the test run cannot create a MySQL test database.

**Consequence.** After approval, migrate `0009` and put each officer in HR or Payroll. Do not deploy until that approval. The Django admin still shows full bank account numbers; the HR file shows the last four digits.
