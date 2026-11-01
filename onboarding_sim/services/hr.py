"""Transactional HR lifecycle operations for Build 03."""
from datetime import date, datetime, timezone, timedelta
import re

from onboarding_sim.database import transaction
from onboarding_sim.services.workflows import append_audit


def _next_id(conn, table, column, prefix, width=6):
    row = conn.execute(f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1").fetchone()
    number = 0
    if row:
        match = re.search(r"(\d+)$", row[0] or "")
        if match:
            number = int(match.group(1))
    return f"{prefix}{number + 1:0{width}d}"


def _event_id(conn):
    return _next_id(conn, "audit_events", "event_id", "EVT-HR-", 8)


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a valid date (YYYY-MM-DD)")


def _notify(conn, role, kind, entity_type, entity_id, message, created_at):
    nid = _next_id(conn, "notifications", "notification_id", "NTF-", 8)
    conn.execute(
        "INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at) VALUES(?,?,?,?,?,?,?)",
        (nid, role, kind, entity_type, entity_id, message, created_at),
    )


def create_employee(conn, data, actor):
    """Create an employee, onboarding case and tasks atomically."""
    name = (data.get("full_name") or "").strip()
    email = (data.get("work_email") or "").strip().lower()
    worker_type = (data.get("worker_type") or "EMPLOYEE").upper()
    role_id = (data.get("role_id") or "").strip()
    manager_id = (data.get("manager_id") or "").strip() or None
    location = (data.get("location") or "").strip()
    hire_date = (data.get("hire_date") or "").strip()
    start_date = (data.get("start_date") or "").strip()
    contract_end = (data.get("contract_end_date") or "").strip() or None
    notes = (data.get("hr_notes") or "").strip()
    if not all((name, email, role_id, location, hire_date, start_date)):
        raise ValueError("Complete all required employee fields")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid company email address")
    if worker_type not in ("EMPLOYEE", "CONTRACTOR", "INTERN", "TEMPORARY"):
        raise ValueError("Select a valid worker type")
    hire, start = _date(hire_date, "Hire date"), _date(start_date, "Start date")
    if start < hire:
        raise ValueError("Start date cannot be earlier than hire date")
    if contract_end:
        if _date(contract_end, "Contract end date") < start:
            raise ValueError("Contract end date cannot be earlier than start date")
    role = conn.execute("SELECT * FROM roles WHERE role_id=? AND active_flag=1", (role_id,)).fetchone()
    if not role:
        raise ValueError("Selected job role is unavailable")
    if manager_id:
        manager = conn.execute("SELECT employee_id FROM employees WHERE employee_id=? AND employment_status='ACTIVE'", (manager_id,)).fetchone()
        if not manager:
            raise ValueError("Select an active manager")
    if conn.execute("SELECT 1 FROM employees WHERE lower(work_email)=?", (email,)).fetchone():
        raise ValueError("An employee already exists with this email")
    if worker_type == "CONTRACTOR" and not contract_end:
        raise ValueError("Contractors must have a contract end date")

    created_at = _now()
    templates = conn.execute("SELECT * FROM task_templates ORDER BY template_id").fetchall()
    if not templates:
        raise ValueError("Onboarding task templates are missing; initialize the dataset before creating employees")
    with transaction(conn):
        employee_id = _next_id(conn, "employees", "employee_id", "EMP-", 6)
        case_id = _next_id(conn, "onboarding_cases", "case_id", f"ONB-{start.year}-", 6)
        status = "PRE_BOARDING"
        conn.execute(
            """INSERT INTO employees(employee_id,full_name,work_email,worker_type,role_id,department_id,manager_id,
               hire_date,start_date,original_start_date,contract_end_date,employment_status,location,hr_notes)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (employee_id, name, email, worker_type, role_id, role["department_id"], manager_id,
             hire_date, start_date, start_date, contract_end, status, location, notes),
        )
        conn.execute(
            "INSERT INTO onboarding_cases(case_id,employee_id,case_type,status,opened_date,planned_start_date) VALUES(?,?,?,?,?,?)",
            (case_id, employee_id, "CONTRACTOR" if worker_type == "CONTRACTOR" else "NEW_HIRE", "IN_PROGRESS", hire_date, start_date),
        )
        for index, template in enumerate(templates, 1):
            due = (start - timedelta(days=3)).isoformat()
            conn.execute(
                """INSERT INTO tasks(task_id,case_id,case_type,template_id,owner_team,task_type,title,status,due_date,sla_hours,priority)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (f"TASK-{case_id}-{index:03d}", case_id, "ONBOARDING", template["template_id"], template["owner_team"],
                 template["task_type"], template["title"], "PENDING", due, template["sla_hours"], "NORMAL"),
            )
        append_audit(conn, _event_id(conn), actor["user_id"], actor["app_role"], "EMPLOYEE_CREATED", "Employee",
                     employee_id, None, status, "HR created employee and onboarding case", created_at)
        _notify(conn, "MANAGER", "ONBOARDING_CREATED", "OnboardingCase", case_id,
                f"Onboarding case created for {name}; manager review may be required.", created_at)
    return {"employee_id": employee_id, "case_id": case_id, "tasks_created": len(templates)}


def change_employee_role(conn, employee_id, role_id, effective_date, reason, actor):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required for a role change")
    effective = _date(effective_date, "Effective date")
    if effective > date.today():
        raise ValueError("Future-dated role changes are not supported; use an effective date of today or earlier")
    with transaction(conn):
        employee = conn.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,)).fetchone()
        role = conn.execute("SELECT * FROM roles WHERE role_id=? AND active_flag=1", (role_id,)).fetchone()
        if not employee:
            raise ValueError("Employee not found")
        if employee["employment_status"] == "TERMINATED":
            raise ValueError("A terminated employee's role cannot be changed")
        if not role:
            raise ValueError("Selected job role is unavailable")
        old = f"{employee['role_id']}|{employee['department_id']}"
        new = f"{role_id}|{role['department_id']}"
        if old == new:
            raise ValueError("Employee already has this role")
        conn.execute("UPDATE employees SET role_id=?,department_id=? WHERE employee_id=?", (role_id, role["department_id"], employee_id))
        decision_id = _next_id(conn, "workflow_decisions", "decision_id", "DEC-HR-", 8)
        now = _now()
        conn.execute(
            "INSERT INTO workflow_decisions(decision_id,decision_type,rule_id,inputs_ref,outcome,reason,created_at) VALUES(?,?,?,?,?,?,?)",
            (decision_id, "ROLE_CHANGE", "HR-ROLE-CHANGE", employee_id, "APPLIED", f"Effective {effective_date}: {reason}", now),
        )
        append_audit(conn, _event_id(conn), actor["user_id"], actor["app_role"], "EMPLOYEE_ROLE_CHANGED", "Employee",
                     employee_id, old, new, reason, now)
    return {"employee_id": employee_id, "old_role_id": employee["role_id"], "new_role_id": role_id, "decision_id": decision_id}


def change_start_date(conn, employee_id, new_start_date, reason, actor):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required for a start-date change")
    _date(new_start_date, "New start date")
    with transaction(conn):
        employee = conn.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,)).fetchone()
        if not employee:
            raise ValueError("Employee not found")
        if employee["employment_status"] == "TERMINATED":
            raise ValueError("A terminated employee's start date cannot be changed")
        if employee["employment_status"] != "PRE_BOARDING":
            raise ValueError("Start-date changes are limited to employees in preboarding")
        if _date(new_start_date, "New start date") < _date(employee["hire_date"], "Hire date"):
            raise ValueError("New start date cannot be earlier than hire date")
        old = employee["start_date"]
        conn.execute("UPDATE employees SET start_date=? WHERE employee_id=?", (new_start_date, employee_id))
        conn.execute("UPDATE onboarding_cases SET planned_start_date=? WHERE employee_id=? AND status!='COMPLETED'", (new_start_date, employee_id))
        due_date = (_date(new_start_date, "New start date") - timedelta(days=3)).isoformat()
        conn.execute("UPDATE tasks SET due_date=? WHERE case_id IN (SELECT case_id FROM onboarding_cases WHERE employee_id=? AND status!='COMPLETED') AND status NOT IN ('DONE','CANCELLED')", (due_date, employee_id))
        now = _now()
        append_audit(conn, _event_id(conn), actor["user_id"], actor["app_role"], "START_DATE_CHANGED", "Employee",
                     employee_id, old, new_start_date, reason, now)
    return {"employee_id": employee_id, "old_start_date": old, "new_start_date": new_start_date}


def terminate_employee(conn, employee_id, last_working_day, termination_type, reason, actor):
    reason = (reason or "").strip()
    termination_type = (termination_type or "").upper()
    if not reason:
        raise ValueError("A termination reason is required")
    if termination_type not in ("VOLUNTARY", "INVOLUNTARY", "CONTRACT_END", "URGENT"):
        raise ValueError("Select a valid termination type")
    last_day = _date(last_working_day, "Last working day")
    now = _now()
    with transaction(conn):
        employee = conn.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,)).fetchone()
        if not employee:
            raise ValueError("Employee not found")
        if employee["employment_status"] == "TERMINATED":
            raise ValueError("Employee is already terminated")
        if last_day < _date(employee["hire_date"], "Hire date"):
            raise ValueError("Last working day cannot be earlier than hire date")
        offboarding_id = _next_id(conn, "offboarding_cases", "offboarding_id", f"OFF-{last_day.year}-", 6)
        conn.execute(
            "UPDATE employees SET employment_status='TERMINATED',termination_date=?,termination_type=? WHERE employee_id=?",
            (last_working_day, termination_type, employee_id),
        )
        conn.execute(
            "INSERT INTO offboarding_cases(offboarding_id,employee_id,termination_type,notice_date,last_working_day,status,is_urgent,hr_reason) VALUES(?,?,?,?,?,?,?,?)",
            (offboarding_id, employee_id, termination_type, date.today().isoformat(), last_working_day, "IN_PROGRESS", int(termination_type == "URGENT"), reason),
        )
        tasks = [
            ("HR", "EXIT_INTERVIEW", "Schedule exit interview", 48),
            ("IT", "REVOKE_ACCESS", "Revoke employee system access", 4 if termination_type == "URGENT" else 24),
            ("IT", "RECOVER_ASSETS", "Recover assigned company assets", 24),
            ("MANAGER", "HANDOVER", "Complete team handover", 48),
            ("FACILITIES", "BADGE_RETURN", "Disable and recover building badge", 24),
            ("HR", "FINAL_PAY", "Prepare final payroll and documents", 72),
        ]
        for index, (team, kind, title, sla) in enumerate(tasks, 1):
            conn.execute(
                "INSERT INTO tasks(task_id,case_id,case_type,owner_team,task_type,title,status,due_date,sla_hours,priority) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (f"TASK-{offboarding_id}-{index:03d}", offboarding_id, "OFFBOARDING", team, kind, title,
                 "READY", last_working_day, sla, "URGENT" if termination_type == "URGENT" else "HIGH"),
            )
        append_audit(conn, _event_id(conn), actor["user_id"], actor["app_role"], "EMPLOYEE_TERMINATED", "Employee",
                     employee_id, employee["employment_status"], "TERMINATED", reason, now)
        _notify(conn, "IT", "OFFBOARDING_STARTED", "OffboardingCase", offboarding_id,
                f"Offboarding started for {employee['full_name']}; revoke access and recover assets by {last_working_day}.", now)
        _notify(conn, "MANAGER", "OFFBOARDING_STARTED", "OffboardingCase", offboarding_id,
                f"Offboarding started for {employee['full_name']}; complete handover by {last_working_day}.", now)
    return {"employee_id": employee_id, "offboarding_id": offboarding_id, "tasks_created": len(tasks)}
