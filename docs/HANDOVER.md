# Handover

## Branch
`feat/hr-employee-records`, one local commit on top of `main` (`4872375`): "HR suite phase 1: employee records, access groups, docs". Not pushed. The working tree is clean after that commit. The commit includes the rules, docs, and `.gitignore` changes that were uncommitted before.

## In progress
Phase 1 employee records are built and the Django suite is green (14 tests). Nothing is deployed. Migration `employee/0009_hr_employee_records` is not applied to the local `payroll` database: MySQL returned access denied for the configured user, so that database was left unchanged.

The HR desk is `/hr/`. Groups `HR` and `Payroll` are created by the migration. HR edits the file. Payroll can open it and download documents. Staff in neither group get the no-access page. Payslip maths was not changed.

## Next
1. Review the diff and commit on `feat/hr-employee-records` when you want it saved.
2. On a machine that can log in to MySQL, run `python manage.py migrate` and click through sign-in, add employee, contract, qualification, history, and document upload with fake data.
3. Put officers in the HR or Payroll group. Do not upload to cPanel or migrate production until you approve that step.

## Gotchas
- `Employee.company` is nullable so existing people can migrate. The HR form still requires a company. Until a company is set, HR and Payroll can see that person.
- A company is visible to the organisation when its owner is in HR or Payroll. An owner outside those groups is visible to that owner and to the person who created the employee.
- The HR file masks the bank account. Django admin still shows the full number.
- Documents go to `hr_documents/` (gitignored), not the current media path.
- `python manage.py test` uses in-memory SQLite. `runserver` and `migrate` still use MySQL.
- These `yehuda-*` files are project overrides. `scripts/dev_sync_rules.py --write` would put the shared Next.js / Railway skills back.
- Git on this machine reports dubious ownership of `D:/Projects/QR/Payroll`. Status was read with a one-off `safe.directory` override. Do not change git config to clear that.
- Remote: `origin` = `https://github.com/sirthom9123/django-payroll.git`. It was switched from SSH because GitHub rejects this PC's SSH key (`Permission denied (publickey)`). `gh` is logged in as `tmotshabi` with write access.
- `origin/main` is `6984777`, two commits ahead of local `main`. It is a fast-forward, not yet pulled. The feature branch is not pushed, and it was not rebased onto `origin/main`.
- `.gitignore` excludes `static/` (any folder), `media/`, `.cursor/`, `.claude/`, `CLAUDE.md`, and `AGENTS.md`. The 131 Django admin assets that were under `static/` are untracked in this commit. They stay on disk. The next push deletes them from the remote, so cPanel needs `collectstatic`.
- `employee/static/hr/hr.css` is excluded by the `static/` rule, but the HR pages need it. Serve it from another path before deploy.

## Commands
`python manage.py test --noinput` · `python manage.py runserver`
