
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS departments(department_id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,cost_center TEXT NOT NULL,location_mode TEXT NOT NULL,head_manager_id TEXT);
CREATE TABLE IF NOT EXISTS roles(role_id TEXT PRIMARY KEY,title TEXT NOT NULL,department_id TEXT NOT NULL REFERENCES departments(department_id),job_family TEXT NOT NULL,level INTEGER NOT NULL,default_worker_type TEXT NOT NULL,requires_equipment_profile INTEGER NOT NULL,risk_tier TEXT NOT NULL,active_flag INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS employees(employee_id TEXT PRIMARY KEY,full_name TEXT NOT NULL,work_email TEXT UNIQUE NOT NULL,worker_type TEXT NOT NULL,role_id TEXT NOT NULL REFERENCES roles(role_id),department_id TEXT NOT NULL REFERENCES departments(department_id),manager_id TEXT REFERENCES employees(employee_id),hire_date TEXT NOT NULL,start_date TEXT NOT NULL,original_start_date TEXT NOT NULL,contract_end_date TEXT,employment_status TEXT NOT NULL,termination_date TEXT,termination_type TEXT,location TEXT NOT NULL,hr_notes TEXT);
CREATE TABLE IF NOT EXISTS managers(manager_id TEXT PRIMARY KEY REFERENCES employees(employee_id),department_id TEXT NOT NULL REFERENCES departments(department_id),can_approve_access INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS onboarding_cases(case_id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES employees(employee_id),case_type TEXT NOT NULL,status TEXT NOT NULL,opened_date TEXT NOT NULL,planned_start_date TEXT NOT NULL,actual_start_date TEXT,completed_date TEXT);
CREATE TABLE IF NOT EXISTS task_templates(template_id TEXT PRIMARY KEY,title TEXT NOT NULL,owner_team TEXT NOT NULL,task_type TEXT NOT NULL,optional_flag INTEGER NOT NULL DEFAULT 0,sla_hours INTEGER NOT NULL DEFAULT 48);
CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,case_type TEXT NOT NULL,template_id TEXT REFERENCES task_templates(template_id),owner_team TEXT NOT NULL,task_type TEXT NOT NULL,title TEXT NOT NULL,status TEXT NOT NULL,due_date TEXT NOT NULL,completed_date TEXT,sla_hours INTEGER NOT NULL,priority TEXT NOT NULL DEFAULT 'NORMAL');
CREATE TABLE IF NOT EXISTS dependencies(dependency_id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(task_id),depends_on_task_id TEXT NOT NULL REFERENCES tasks(task_id),dependency_type TEXT NOT NULL DEFAULT 'FINISH_TO_START',UNIQUE(task_id,depends_on_task_id),CHECK(task_id<>depends_on_task_id));
CREATE TABLE IF NOT EXISTS access_roles(access_role_id TEXT PRIMARY KEY,system_name TEXT NOT NULL,privilege_level TEXT NOT NULL,requires_approval INTEGER NOT NULL,approver_type TEXT NOT NULL,max_duration_days INTEGER);
CREATE TABLE IF NOT EXISTS role_access_roles(role_id TEXT NOT NULL REFERENCES roles(role_id),access_role_id TEXT NOT NULL REFERENCES access_roles(access_role_id),effective_from TEXT NOT NULL,effective_to TEXT,PRIMARY KEY(role_id,access_role_id,effective_from));
CREATE TABLE IF NOT EXISTS approvals(approval_id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES employees(employee_id),request_type TEXT NOT NULL,approver_id TEXT,decision TEXT NOT NULL,reason TEXT NOT NULL,decided_at TEXT);
CREATE TABLE IF NOT EXISTS access_grants(grant_id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES employees(employee_id),access_role_id TEXT NOT NULL REFERENCES access_roles(access_role_id),approval_id TEXT REFERENCES approvals(approval_id),requested_date TEXT NOT NULL,approved_date TEXT,granted_date TEXT,effective_from TEXT NOT NULL,effective_to TEXT,revoked_date TEXT,status TEXT NOT NULL,granted_by TEXT);
CREATE TABLE IF NOT EXISTS assets(asset_id TEXT PRIMARY KEY,asset_type TEXT NOT NULL,serial_number TEXT UNIQUE NOT NULL,model TEXT NOT NULL,purchase_date TEXT NOT NULL,current_status TEXT NOT NULL,current_holder_employee_id TEXT REFERENCES employees(employee_id));
CREATE TABLE IF NOT EXISTS asset_assignments(assignment_id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES assets(asset_id),employee_id TEXT NOT NULL REFERENCES employees(employee_id),assigned_date TEXT NOT NULL,delivery_date TEXT,acknowledged_date TEXT,recovery_due_date TEXT,recovered_date TEXT,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offboarding_cases(offboarding_id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES employees(employee_id),termination_type TEXT NOT NULL,notice_date TEXT NOT NULL,last_working_day TEXT NOT NULL,status TEXT NOT NULL,is_urgent INTEGER NOT NULL DEFAULT 0,completed_date TEXT,hr_reason TEXT);
CREATE TABLE IF NOT EXISTS audit_events(event_id TEXT PRIMARY KEY,event_ts TEXT NOT NULL,actor_id TEXT NOT NULL,actor_role TEXT NOT NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,from_state TEXT,to_state TEXT,reason TEXT NOT NULL,override_flag INTEGER NOT NULL DEFAULT 0,related_case_id TEXT,correlation_id TEXT);
CREATE TABLE IF NOT EXISTS user_accounts(user_id TEXT PRIMARY KEY,employee_id TEXT UNIQUE REFERENCES employees(employee_id),email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,app_role TEXT NOT NULL,account_status TEXT NOT NULL,failed_login_count INTEGER NOT NULL DEFAULT 0,locked_until TEXT,created_at TEXT NOT NULL,last_login_at TEXT,approved_by TEXT,must_change_password INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS permissions(permission_id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS role_permissions(app_role TEXT NOT NULL,permission_id TEXT NOT NULL REFERENCES permissions(permission_id),PRIMARY KEY(app_role,permission_id));
CREATE TABLE IF NOT EXISTS access_requests(request_id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES employees(employee_id),access_role_id TEXT NOT NULL REFERENCES access_roles(access_role_id),business_justification TEXT NOT NULL,status TEXT NOT NULL,manager_decision TEXT,it_decision TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(notification_id TEXT PRIMARY KEY,recipient_user_id TEXT,recipient_role TEXT,type TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,message TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_decisions(decision_id TEXT PRIMARY KEY,case_id TEXT,decision_type TEXT NOT NULL,rule_id TEXT NOT NULL,inputs_ref TEXT NOT NULL,outcome TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exception_records(exception_id TEXT PRIMARY KEY,issue_type TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,severity TEXT NOT NULL,status TEXT NOT NULL,rule_id TEXT NOT NULL,description TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reconciliation_results(reconciliation_id TEXT PRIMARY KEY,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,status TEXT NOT NULL,details TEXT NOT NULL,checked_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tasks_case ON tasks(case_id);
CREATE INDEX IF NOT EXISTS idx_grants_employee ON access_grants(employee_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type,entity_id);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'Audit events are append-only'); END;

CREATE TABLE IF NOT EXISTS employee_documents(
 document_id TEXT PRIMARY KEY,
 employee_id TEXT NOT NULL REFERENCES employees(employee_id),
 uploaded_by TEXT NOT NULL,
 document_type TEXT NOT NULL,
 original_filename TEXT NOT NULL,
 stored_filename TEXT NOT NULL UNIQUE,
 content_type TEXT NOT NULL,
 file_size INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
 review_note TEXT,
 reviewed_by TEXT,
 uploaded_at TEXT NOT NULL,
 reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_employee_documents_employee ON employee_documents(employee_id, uploaded_at);
CREATE INDEX IF NOT EXISTS idx_employee_documents_status ON employee_documents(status, uploaded_at);
