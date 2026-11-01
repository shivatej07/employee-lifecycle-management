# Build 06 — Employee Self-Service Portal

## Delivered in this increment

- Employee dashboard now displays the signed-in employee's own lifecycle status, onboarding tasks, equipment assignments, access requests and notifications.
- Employee access requests are created in `PENDING_MANAGER`; the employee cannot approve or provision their own request.
- Employee task completion is restricted to tasks attached to that employee's onboarding case and assigned to the employee team. Existing dependency checks remain enforced by the workflow service.
- Equipment acknowledgement is allowed only for a `DELIVERED` assignment belonging to the signed-in employee. It records the acknowledgement date, changes the assignment to `ACKNOWLEDGED`, appends an audit event and notifies IT.
- Notification read state can be updated for the signed-in user's own notifications.
- Employee routes reject other roles; employee asset/task operations use employee ownership checks to prevent IDOR access.
- IT recovery and reconciliation now treat `ACKNOWLEDGED` equipment as an active assignment, so acknowledged equipment can still be recovered during offboarding.

## Routes

- `GET /portal/employee`
- `POST /employee/tasks/{task_id}/complete`
- `POST /employee/access-requests`
- `POST /employee/assets/{assignment_id}/acknowledge`
- `POST /employee/notifications/read`

## Verification

Run `python -m pytest -q`. The employee portal tests cover dashboard rendering, role boundaries, access-request submission, equipment acknowledgement and cross-employee ownership denial.

## Remaining work

This increment does not yet implement secure document upload, employee-side offboarding confirmations, full notification routing/preferences, CSRF protection or the final security hardening required by the master prompt. The overall project remains in progress and is not the final submission build.
