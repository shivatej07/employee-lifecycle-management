# Manager Portal — Build 04

## Available workspace

After signing in with a MANAGER account, the portal links to:

- `/manager/team` — direct reports only, with employee status, role, department, start date and onboarding completion percentage.
- `/manager/access-requests` — access requests for direct reports in `PENDING_MANAGER`, `REQUESTED` or `REVERIFICATION_REQUESTED` states.
- `/manager/tasks` — onboarding tasks for direct reports, with an optional status filter.

## Access request decisions

A manager can submit one of three decisions with a mandatory reason:

1. `APPROVE` — records the manager approval, changes the request to `PENDING_IT`, writes an append-only audit event and notifies IT. It does not provision access.
2. `REJECT` — records the rejection, changes the request to `MANAGER_REJECTED`, writes an audit event and notifies HR.
3. `REVERIFY` — records that the request needs further verification and keeps it visible in the manager review queue.

Only a manager linked to the employee's `manager_id` may decide that employee's request. A request outside the manager's direct-report scope is rejected by the service. A previously decided request cannot be decided again.

## Data dependencies and current boundaries

The access-request queue reads `access_requests`. The full deterministic demo dataset seeds one pending sample request for each manager with an eligible direct report (156 requests in the current full seed); the demo manager account has three requests in its queue. These are clearly synthetic demonstration requests. Employee self-service request submission is scheduled for Build 06. Manager decisions are deliberately separate from IT provisioning, which is scheduled for Build 05.

The task view is read-only. Task completion and employee-owned tasks are part of the Employee Portal build. This build does not claim to implement all security controls in the master requirements; CSRF protection and additional session hardening remain in the security build.

## Verification

`tests/test_manager_portal.py` covers team scope, task visibility, approval state changes, IT notification, duplicate-decision rejection and authenticated route behavior. Run `python -m pytest -v` from the project root.
