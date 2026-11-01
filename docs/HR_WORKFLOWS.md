# HR Portal — Build 03

## Available HR operations

The HR workspace is available to authenticated accounts whose application role is `HR`.

1. **Employee directory** — search by employee ID, name or work email; review up to 100 matching records.
2. **Create employee** — create a worker record and onboarding case in one database transaction. Active job roles, active managers, worker type, dates, work location and HR notes are captured. Contractors require a contract end date.
3. **Create onboarding tasks** — every active task template is instantiated for the new case. The generated tasks begin in `PENDING` and use the planned start date to calculate a due date three days before start.
4. **Change job role** — update the role and department together, record an explicit workflow decision and append an audit event with the HR reason. Future-dated role changes are not supported in this increment.
5. **Change planned start date** — limited to `PRE_BOARDING` employees. The employee and open onboarding case are updated, and unfinished onboarding task due dates are recalculated. A reason is mandatory.
6. **Initiate termination** — mark the employee terminated, create an offboarding case, create six work items for HR, IT, Manager and Facilities, append an audit event, and notify IT and Manager role inboxes. Urgent termination gives the access-revocation task a four-hour SLA.

## Atomicity and traceability

Employee creation, role changes, start-date changes and termination run inside SQLite `BEGIN IMMEDIATE` transactions. Each successful state transition writes an append-only `audit_events` record. Role changes also write a `workflow_decisions` record. Failed validation is rejected before mutation or rolled back.

## Routes

- `GET /hr/employees`
- `GET /hr/employees/new`
- `POST /hr/employees`
- `GET /hr/employees/{employee_id}`
- `POST /hr/employees/{employee_id}/role`
- `POST /hr/employees/{employee_id}/start-date`
- `POST /hr/employees/{employee_id}/terminate`

All routes require an authenticated HR role. Other authenticated roles receive HTTP 403.

## Known boundaries for later builds

- This increment does not yet implement invitation emails, employee self-service document uploads, manager approval queues, access-request approval, IT provisioning/revocation execution, asset issue/acknowledgement/recovery, or offboarding completion/reconciliation.
- Termination is recorded as an immediate `TERMINATED` state in this increment; scheduled future-effective termination needs a dedicated state transition design.
- Session/CSRF hardening and comprehensive audit review are assigned to the security build.
