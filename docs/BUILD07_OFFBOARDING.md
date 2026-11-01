# Build 07 — Complete Offboarding Workflow

## Implemented
- HR offboarding case queue and case detail view.
- HR termination remains the entry point and creates explicit exit tasks with urgency/SLA values.
- Manager sees only offboarding handovers for employees who directly report to them and can complete the handover with a mandatory note.
- IT sees open offboarding cases and can revoke active access grants and recover outstanding assets using existing audited IT operations.
- IT can complete IT and Facilities exit tasks with a mandatory completion note.
- HR can complete HR exit tasks and close a case only after all offboarding tasks are DONE/CANCELLED, no access grant remains GRANTED, and no asset assignment remains unrecovered.
- Task completion and case closure create append-only audit events. Task completion also creates a workflow decision.
- HR receives a completion notification when a case is closed.

## Navigation
- HR: `/hr/offboarding`
- Manager: `/manager/offboarding`
- IT / Operations: `/it/offboarding`

## Important business rules
- An HR user cannot close a case while tasks, active grants, or unrecovered assets remain.
- A manager can complete only a handover task belonging to a direct report.
- IT can act only on IT/Facilities exit tasks and uses the existing revoke/recover services.
- All completion notes are mandatory.
- Urgent exits are visibly prioritized in HR and IT queues; IT revocation tasks have a 4-hour SLA for urgent exits.

## Verification
Run `python -m pytest -q`. Build 07 adds service tests for closure blockers, task completion audit, and successful closure.
