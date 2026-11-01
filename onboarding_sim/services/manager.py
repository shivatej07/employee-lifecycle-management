"""Manager team, readiness and access-approval operations (Build 04)."""
from datetime import datetime, timezone
import re

from onboarding_sim.database import transaction
from onboarding_sim.services.workflows import append_audit


def _next_id(conn, table, column, prefix, width=8):
    row = conn.execute(f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1").fetchone()
    number = 0
    if row:
        match = re.search(r"(\d+)$", row[0] or "")
        if match:
            number = int(match.group(1))
    return f"{prefix}{number + 1:0{width}d}"


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _team_employee(conn, manager_employee_id, employee_id):
    row = conn.execute(
        "SELECT employee_id,full_name,employment_status FROM employees WHERE employee_id=? AND manager_id=?",
        (employee_id, manager_employee_id),
    ).fetchone()
    if not row:
        raise ValueError("Employee is not a direct report of this manager")
    return row


def team_overview(conn, manager_employee_id):
    """Return direct reports with onboarding progress and open task counts."""
    rows = conn.execute(
        """SELECT e.employee_id,e.full_name,e.work_email,e.employment_status,e.start_date,
                  r.title AS role_title,d.name AS department_name,
                  COUNT(t.task_id) AS total_tasks,
                  SUM(CASE WHEN t.status='DONE' THEN 1 ELSE 0 END) AS done_tasks,
                  SUM(CASE WHEN t.status NOT IN ('DONE','CANCELLED') THEN 1 ELSE 0 END) AS open_tasks
           FROM employees e
           LEFT JOIN roles r ON r.role_id=e.role_id
           LEFT JOIN departments d ON d.department_id=e.department_id
           LEFT JOIN onboarding_cases oc ON oc.employee_id=e.employee_id AND oc.status!='COMPLETED'
           LEFT JOIN tasks t ON t.case_id=oc.case_id
           WHERE e.manager_id=?
           GROUP BY e.employee_id ORDER BY e.start_date,e.full_name""",
        (manager_employee_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        total = item.get("total_tasks") or 0
        done = item.get("done_tasks") or 0
        item["readiness_percent"] = round(done * 100 / total) if total else 100
        result.append(item)
    return result


def pending_access_requests(conn, manager_employee_id):
    return conn.execute(
        """SELECT ar.request_id,ar.employee_id,e.full_name,e.work_email,ar.access_role_id,
                  ac.system_name,ac.privilege_level,ar.business_justification,ar.status,ar.created_at
           FROM access_requests ar
           JOIN employees e ON e.employee_id=ar.employee_id
           JOIN access_roles ac ON ac.access_role_id=ar.access_role_id
           WHERE e.manager_id=? AND ar.status IN ('PENDING_MANAGER','REQUESTED','REVERIFICATION_REQUESTED')
           ORDER BY ar.created_at,ar.request_id""",
        (manager_employee_id,),
    ).fetchall()


def team_tasks(conn, manager_employee_id, status=None):
    sql = """SELECT t.task_id,t.title,t.status,t.due_date,t.owner_team,t.priority,
                    e.employee_id,e.full_name,oc.case_id
             FROM tasks t JOIN onboarding_cases oc ON oc.case_id=t.case_id
             JOIN employees e ON e.employee_id=oc.employee_id
             WHERE e.manager_id=? AND t.case_type='ONBOARDING'"""
    params = [manager_employee_id]
    if status:
        sql += " AND t.status=?"
        params.append(status)
    sql += " ORDER BY t.due_date,t.task_id LIMIT 500"
    return conn.execute(sql, params).fetchall()


def decide_access_request(conn, request_id, decision, reason, actor):
    """Manager decision. IT provisioning is intentionally a separate IT action."""
    decision = (decision or "").strip().upper()
    reason = (reason or "").strip()
    if decision not in ("APPROVE", "REJECT", "REVERIFY"):
        raise ValueError("Decision must be APPROVE, REJECT or REVERIFY")
    if not reason:
        raise ValueError("A decision reason is required")
    manager_employee_id = actor.get("employee_id")
    if not manager_employee_id:
        raise ValueError("Manager account is not linked to an employee record")

    row = conn.execute(
        """SELECT ar.*,e.manager_id,e.full_name FROM access_requests ar
           JOIN employees e ON e.employee_id=ar.employee_id WHERE ar.request_id=?""",
        (request_id,),
    ).fetchone()
    if not row:
        raise ValueError("Access request not found")
    if row["manager_id"] != manager_employee_id:
        raise ValueError("Access request is outside your team")
    if row["status"] not in ("PENDING_MANAGER", "REQUESTED", "REVERIFICATION_REQUESTED"):
        raise ValueError("This access request has already been decided or is not awaiting manager review")

    status_map = {
        "APPROVE": ("PENDING_IT", "APPROVED"),
        "REJECT": ("MANAGER_REJECTED", "REJECTED"),
        "REVERIFY": ("REVERIFICATION_REQUESTED", "REVERIFY"),
    }
    new_status, manager_decision = status_map[decision]
    now = _now()
    with transaction(conn):
        conn.execute(
            "UPDATE access_requests SET status=?,manager_decision=? WHERE request_id=?",
            (new_status, manager_decision, request_id),
        )
        approval_id = _next_id(conn, "approvals", "approval_id", "APR-", 6)
        conn.execute(
            """INSERT INTO approvals(approval_id,employee_id,request_type,approver_id,decision,reason,decided_at)
               VALUES(?,?,?,?,?,?,?)""",
            (approval_id, row["employee_id"], "ACCESS", manager_employee_id, manager_decision, reason, now),
        )
        event_id = _next_id(conn, "audit_events", "event_id", "EVT-MGR-", 8)
        append_audit(
            conn, event_id, actor["user_id"], "MANAGER", f"ACCESS_REQUEST_{decision}",
            "AccessRequest", request_id, row["status"], new_status, reason, now,
        )
        notification_id = _next_id(conn, "notifications", "notification_id", "NTF-", 8)
        recipient_role = "IT" if decision == "APPROVE" else "HR"
        message = {
            "APPROVE": f"Manager approved access request {request_id}; IT review is pending.",
            "REJECT": f"Access request {request_id} was rejected by the manager: {reason}",
            "REVERIFY": f"Access request {request_id} requires re-verification: {reason}",
        }[decision]
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (notification_id, recipient_role, f"ACCESS_{decision}", "AccessRequest", request_id, message, now),
        )
    return {"request_id": request_id, "status": new_status, "approval_id": approval_id}
