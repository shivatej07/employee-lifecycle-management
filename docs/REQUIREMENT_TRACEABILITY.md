# Requirement Traceability — Incremental Register

| Requirement area | Build | Implementation | Verification | Status |
|---|---:|---|---|---|
| FastAPI application, SQLite schema, CLI, deterministic generator | 01 | `onboarding_sim/`, `schema.sql`, `__main__.py` | `tests/test_foundation.py`, `tests/test_coverage_paths.py` | Foundation implemented |
| Six anomaly categories and independent detector | 02 | `detection/core.py`, `generator/core.py` | `tests/test_detector.py` | Verified on generated full dataset |
| HR employee directory and search | 03 | `web/main.py` `/hr/employees` | `tests/test_hr_portal.py` | Implemented and tested |
| HR create employee and onboarding case/tasks | 03 | `services/hr.py:create_employee` | `test_hr_create_employee_role_change_start_date_and_termination`, `test_hr_web_portal_create_and_role_access` | Implemented and tested |
| HR role changes with reason and audit | 03 | `services/hr.py:change_employee_role` | HR service and web integration tests | Implemented and tested |
| HR preboarding start-date change | 03 | `services/hr.py:change_start_date` | HR service and web integration tests | Implemented and tested |
| HR termination/offboarding initiation | 03 | `services/hr.py:terminate_employee` | HR service and web integration tests | Initiation implemented; completion gates pending |
| Manager request approvals/rejections | 04 | Pending | Pending | Not implemented |
| IT provisioning, revocation and asset workflows | 05 | Pending | Pending | Not implemented |
| Employee self-service and task completion | 06 | Pending | Pending | Not implemented |
| CSRF, lockout, session hardening, comprehensive RBAC/IDOR | 07 | Partial foundations only | Pending | Not complete |
| Search, reports, reconciliation and dashboard drill-downs | 08 | Partial foundations only | Pending | Not complete |
| Final acceptance, documentation and submission package | 09 | Pending | Pending | Not complete |

The original master prompt remains authoritative. This register records incremental implementation and does not imply that unlisted requirements are satisfied.
