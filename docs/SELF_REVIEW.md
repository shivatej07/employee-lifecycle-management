# Self Review — Build 03

## Completed development increments

### Build 01 — Foundation
- FastAPI/Uvicorn app entry point and server-rendered login/register/portal routes.
- SQLite schema with core and supporting tables, FK constraints, indexes and append-only audit triggers.
- Deterministic starter/full generator code and CSV/database exports for core data.
- Basic data validation, task engine, anomaly detector, metrics output, password helpers and scoped employee search.
- CLI entry point, Windows run scripts, requirements and initial project documentation.

### Build 02 — Test and data foundation
- Expanded automated tests for generator, database, validation, workflow engine, reporting, search, demo initialization and CLI dispatch.
- Full-scale anomaly detector test covers all six anomaly categories on the generated full dataset.
- Last verified Build 02 baseline: 25 tests passed; 96% package coverage.

### Build 03 — HR Management Portal
- HR-only employee directory with search.
- Employee creation with role, department, manager, worker type, dates, location and notes.
- Atomic creation of an onboarding case and tasks from the configured task templates.
- Role change with workflow decision and append-only audit event.
- Preboarding start-date change with open-case and unfinished-task due-date updates.
- Termination initiation with offboarding case, six cross-functional tasks, audit event and IT/Manager notifications.
- Role guard tests and HR service validation tests.

## Build 03 verification evidence (2026-10-31)
- `python -m pytest -q`: 28 passed, 0 failed.
- `coverage run --source=onboarding_sim -m pytest -q` followed by `coverage report -m`: 91% total coverage.
- HR lifecycle integration test exercises employee creation, role change, start-date change and termination.
- HR web test exercises HR login, employee directory, employee create form, detail page, role change, start-date change, termination and manager denial (HTTP 403).

## Not yet complete or verified
- Manager approval queues and approval/rejection workflow.
- IT access provisioning/revocation and asset assignment/delivery/acknowledgement/recovery.
- Employee task completion, document submission and employee self-service dashboard.
- Scheduled future-effective termination and full offboarding completion gates.
- Notifications inbox UI and notification read-state actions.
- CSRF protection, login lockout enforcement, robust idle timeout, privileged-account approval and endpoint-by-endpoint IDOR/security testing.
- Full reconciliation, comprehensive global search, dashboard charts/drill-downs, exports and final report pack verification.
- Full browser automation, Windows clean-install acceptance test, and final requirement-by-requirement sign-off.

This remains an incremental development build, not the final submission build. Do not interpret code coverage as requirement completion.
