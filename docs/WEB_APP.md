# Web Application

FastAPI entry point: `onboarding_sim.web.main:app`.

## Current route groups

- Authentication: `/login`, `/register`, `/logout`
- Role portals: `/portal/employee`, `/portal/manager`, `/portal/hr`, `/portal/it`, `/portal/admin`
- HR workspace: `/hr/employees`, `/hr/employees/new`, `/hr/employees/{employee_id}` and HR lifecycle POST actions (see `HR_WORKFLOWS.md`)
- System health: `/admin/health`
- Scoped employee search: `/search`

The HR routes enforce an authenticated `HR` role. Other roles receive HTTP 403. Manager, IT and Employee portals are still early foundations; their full operational workflows are assigned to later builds.


## Build 05 — IT / Operations routes

- `GET /it/access-requests`: manager-approved IT queue.
- `POST /it/access-requests/{request_id}/provision`: provision after policy checks.
- `POST /it/access-requests/{request_id}/reject`: reject with a reason.
- `GET /it/grants`: grant inventory.
- `POST /it/grants/{grant_id}/revoke`: revoke an active grant with a reason.
- `GET /it/assets`: stock, active assignments and reconciliation exceptions.
- `POST /it/assets/assign`: assign an in-stock asset.
- `POST /it/assets/{assignment_id}/deliver`: record delivery.
- `POST /it/assets/{assignment_id}/recover`: record recovery and return the asset to stock.

## Build 06 — Employee self-service routes

- `GET /portal/employee`: personal dashboard with tasks, equipment, access requests and notifications.
- `POST /employee/tasks/{task_id}/complete`: complete an employee-owned task after dependency checks.
- `POST /employee/access-requests`: submit a request into the manager approval queue.
- `POST /employee/assets/{assignment_id}/acknowledge`: acknowledge only equipment delivered to the signed-in employee.
- `POST /employee/notifications/read`: mark the signed-in user's notifications as read.

Employee routes enforce the `EMPLOYEE` role and bind operations to the employee ID stored in the authenticated session. Secure document upload and employee-side offboarding confirmations remain pending.
