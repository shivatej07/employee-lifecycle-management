# Employee Lifecycle Management System

FastAPI + SQLite application for employee onboarding, offboarding, access and asset lifecycle management. Development is delivered in incremental builds; see `docs/SELF_REVIEW.md` for implemented scope and outstanding work.

## Windows CMD setup

```cmd
py -3.11 -m venv dingo
dingo\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python -m onboarding_sim generate --scale starter
python -m onboarding_sim validate
python -m onboarding_sim init-app
python -m onboarding_sim serve
```

Open `http://127.0.0.1:8000`.

## Full synthetic dataset

```cmd
python -m onboarding_sim generate --scale full --seed 20261022
python -m onboarding_sim validate
python -m onboarding_sim report
python -m onboarding_sim reset-app
python -m onboarding_sim serve
```

## Tests and coverage

```cmd
python -m pytest -v
coverage erase
coverage run --source=onboarding_sim -m pytest -q
coverage report -m
```

## Demo accounts

All demo accounts use `Demo@2026!` (local demonstration only):

- `employee.demo@example.invalid`
- `manager.demo@example.invalid`
- `hr.demo@example.invalid`
- `it.demo@example.invalid`
- `admin.demo@example.invalid`

Change demo credentials before any non-demo use. Do not deploy with the development secret key.

## HR portal (Build 03)

After signing in as `hr.demo@example.invalid`, open `/hr/employees` to search employees, create a new employee and onboarding case, change an employee's role or preboarding start date, or initiate offboarding. See `docs/HR_WORKFLOWS.md` for route and workflow details.

## Manager portal (Build 04)

After signing in as `manager.demo@example.invalid`, open `/portal/manager`. The portal links to `/manager/team`, `/manager/access-requests` and `/manager/tasks`. Managers see direct reports only, monitor onboarding readiness, and can approve, reject or request re-verification of access requests with a mandatory reason. Approval moves a request to `PENDING_IT`; it does not provision access. See `docs/MANAGER_WORKFLOWS.md` for details and current dependencies.

The full seeded demo dataset includes synthetic pending access requests so the manager approval queue can be demonstrated before employee self-service request submission arrives in Build 06. IT provisioning/revocation and asset workflows are part of Build 05. Employee self-service, security hardening, reconciliation and final submission checks remain in progress. This is not yet the final acceptance build.


## Build 05 — IT & Operations Portal

The IT / Operations role has dedicated workspaces:

- `/portal/it` — IT dashboard and queue summaries.
- `/it/access-requests` — manager-approved requests awaiting IT provisioning or rejection.
- `/it/grants` — active and revoked access grants, with reason-required revocation.
- `/it/assets` — inventory, assignment, delivery recording, recovery and reconciliation exceptions.

Access provisioning requires a manager-approved request, an approval record when the access role requires approval, a non-terminated employee, and a start date that has arrived. Provisioning and revocation are recorded as audit events. Asset assignment is limited to in-stock assets and non-terminated employees. Delivery and recovery are explicit state transitions; recovery returns the asset to inventory. The reconciliation view reports pre-existing inconsistencies instead of silently repairing them.

IT demo login: `it.demo@example.invalid` / `Demo@2026!`.

See `docs/BUILD05_VERIFICATION.md` for the verified scope, test results and remaining integration work.

## Build 06 — Employee Self-Service Portal

After signing in as `employee.demo@example.invalid`, open `/portal/employee`. The dashboard shows your onboarding tasks, assigned equipment, access requests and notifications. You can submit an access request for manager review, complete employee-owned tasks when prerequisites are satisfied, acknowledge delivered equipment and mark your own notifications as read. Employee actions are scoped to the signed-in employee and recorded in the audit log. See `docs/BUILD06_EMPLOYEE_PORTAL.md` for routes, verification and remaining work.
