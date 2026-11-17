# QA — Phase 1 employee records

**Date.** 2026-11-17
**Build.** `feat/hr-employee-records` (uncommitted)
**Scope.** `/hr/` employee file: list, personal and job, contract, qualification, employment history, document upload and download. Payslip totals must stay on the current rules.

## Risk

Staff auth, another company's file, masked bank numbers, document download, and an accidental change to payslip maths or the payslip view.

## Cases

| ID | Scenario | Expected | Type | Priority | Result |
|---|---|---|---|---|---|
| P1-01 | Logged-out user opens `/hr/` | Redirect to `/accounts/login/` | TestCase | P1 | Pass |
| P1-02 | Staff with no group | No-access page | TestCase | P1 | Pass |
| P1-03 | HR adds a person, contract, two qualifications, history, and a document | Rows saved, download returns the file | TestCase | P1 | Pass |
| P1-04 | Payroll opens the file and posts an edit or upload | File opens, edit and upload return view-only | TestCase | P1 | Pass |
| P1-05 | Employee of a company owned outside HR and Payroll | 404, hidden from the list | TestCase | P1 | Pass |
| P1-06 | Missing ID and passport, bad ID, date departed before hired, fixed-term without an end date | Form redisplays the validation copy, nothing is saved | TestCase | P1 | Pass |
| P1-07 | Bank account on the file | Last four digits only | TestCase | P1 | Pass |
| P1-08 | Home counts | Active employees and this month's payroll runs, leave not captured | TestCase | P2 | Pass |
| P1-09 | Payslip save and PDF | Basic salary is rate × hours, UIF stays on the current 1% rule, anonymous PDF goes to admin login, staff PDF starts with `%PDF` | TestCase | P1 | Pass |
| P1-10 | Desktop click-through in the browser | Sign in, add a fake employee, save each section | Manual | P1 | Not run |

## Evidence

`venv\Scripts\python.exe manage.py test --noinput`

14 tests, OK, about 31 seconds. The payslip PDF run printed xhtml2pdf font warnings and still returned a PDF.

P1-10 was not run. Local MySQL rejected the configured user, so the app was not started against the payroll database and that database was not migrated.

## Bugs

No open defects from the automated run.

## Verdict

**GO** for the phase 1 code on this branch.

**NO-GO** for cPanel. Migrate `0009`, assign the HR and Payroll groups, and click through P1-10 on a machine that can reach MySQL before anything is uploaded.
