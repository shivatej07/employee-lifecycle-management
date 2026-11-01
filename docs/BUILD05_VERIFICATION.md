# Build 05 Verification — IT & Operations

## Implemented
- Manager-approved access request queue for IT.
- IT provisioning with manager approval, required approval-record, employee status and start-date checks.
- IT rejection with a mandatory reason.
- Active access grant listing and reason-required revocation.
- Asset inventory with in-stock assignment, delivery recording and recovery.
- Asset recovery returns the asset to `IN_STOCK` and clears its current holder.
- Audit events for provisioning, rejection, revocation, assignment, delivery and recovery.
- Notifications for provisioning, rejection, assignment and delivery.
- Read-only asset reconciliation exception listing.
- IT role-gated web routes and dashboard navigation.

## Automated verification
- `pytest -q`: 37 passed, 0 failed.
- `coverage run --source=onboarding_sim -m pytest -q` followed by `coverage report -m`: 87% total coverage.
- `python -m onboarding_sim validate`: passed; 0 foreign-key violations; 1,000 employees; 8,000 tasks; 1,500 access grants; 1,200 assets.
- Python imports and route tests exercise the IT web endpoints through FastAPI TestClient.

## Known limitations / next build work
- Employee-side equipment acknowledgement is reserved for Build 06.
- Offboarding-triggered automatic access revocation and end-to-end lifecycle orchestration are not yet complete; these remain integration work.
- The current report command surfaced a ground-truth alignment discrepancy for `OVERRIDE_WITHOUT_AUDIT` and `TERMINATED_EMPLOYEE_RETAINS_GRANT` on the packaged export snapshot. This is not concealed as a successful anomaly evaluation; resolve and rerun the full reproducibility/evaluation pipeline during final integration.
- Browser-based manual verification on the user's Windows machine is still required after extracting this build.

Build 05 is an incremental IT/Operations release, not the final submission.
