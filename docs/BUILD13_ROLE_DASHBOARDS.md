# Build 13 — Role Dashboard Experience

## Purpose
Build 12 improved responsive layout primitives, but the Employee, Manager, HR and IT landing pages still presented mostly plain text, links and lists. Build 13 gives each actor a dedicated operational dashboard while preserving role gates and existing workflow routes.

## Dashboard changes
- Employee: personalized workspace hero, employee identity/status, task/equipment/notification metrics, and existing self-service sections.
- Manager: team, pending access approval and open-task metrics; quick actions; direct-report readiness snapshot.
- HR: workforce metrics, pending document reviews and open offboarding cases; quick actions and employment-status summary.
- IT: provisioning queue, active grants, available stock and manager-review metrics; quick actions and grant-status summary.
- System Administrator: retains the existing control-center dashboard.

## Navigation
The shared header's My dashboard link continues to use the authenticated actor's role-to-portal mapping. Logout remains a single visible Logout action. No role permissions or route access rules were relaxed.

## Responsive presentation
Added reusable hero, quick-action, team snapshot and status-summary components. Layouts collapse from multi-column grids to tablet/mobile arrangements, preserve readable labels and avoid horizontal overflow outside the responsive table wrapper.

## Verification
Run `python -m onboarding_sim reset-app` and `python -m pytest -q`. The dashboard smoke test logs in as each of the five demo actors and checks that the correct portal responds, its role-specific workspace content is present, the My dashboard link targets the correct role portal, and Logout is displayed without Switch actor.
