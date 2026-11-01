"""Employee self-service actions with strict employee ownership checks."""
from datetime import datetime, timezone
import re
from onboarding_sim.database import transaction
from onboarding_sim.services.workflows import append_audit, complete_task


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _next_id(conn, table, column, prefix):
    row = conn.execute(f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1").fetchone()
    n = 0
    if row:
        m = re.search(r"(\d+)$", row[0] or "")
        if m: n = int(m.group(1))
    return f"{prefix}{n+1:08d}"


def dashboard_data(conn, employee_id, user_id):
    employee = conn.execute("SELECT * FROM employees WHERE employee_id=?", (employee_id,)).fetchone()
    if not employee:
        raise ValueError("Employee profile is not linked to this account")
    tasks = conn.execute(
        """SELECT t.*, c.employee_id FROM tasks t JOIN onboarding_cases c ON c.case_id=t.case_id
           WHERE c.employee_id=? ORDER BY CASE t.status WHEN 'READY' THEN 0 WHEN 'IN_PROGRESS' THEN 1 ELSE 2 END, t.due_date""",
        (employee_id,),
    ).fetchall()
    assets = conn.execute(
        """SELECT aa.*,a.asset_type,a.model,a.serial_number FROM asset_assignments aa
           JOIN assets a ON a.asset_id=aa.asset_id WHERE aa.employee_id=? ORDER BY aa.assigned_date DESC""",
        (employee_id,),
    ).fetchall()
    notices = conn.execute(
        "SELECT * FROM notifications WHERE recipient_user_id=? OR (recipient_user_id IS NULL AND recipient_role='EMPLOYEE') ORDER BY created_at DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    requests = conn.execute(
        """SELECT ar.*,r.system_name,r.privilege_level FROM access_requests ar
           JOIN access_roles r ON r.access_role_id=ar.access_role_id WHERE ar.employee_id=? ORDER BY ar.created_at DESC""",
        (employee_id,),
    ).fetchall()
    return employee, tasks, assets, notices, requests


def request_access(conn, employee_id, access_role_id, justification, actor):
    justification = (justification or '').strip()
    if len(justification) < 12:
        raise ValueError('Please provide a business justification of at least 12 characters.')
    employee = conn.execute("SELECT employment_status,start_date FROM employees WHERE employee_id=?", (employee_id,)).fetchone()
    role = conn.execute("SELECT * FROM access_roles WHERE access_role_id=?", (access_role_id,)).fetchone()
    if not employee or employee['employment_status'] == 'TERMINATED':
        raise ValueError('Access requests are unavailable for this employee.')
    if not role:
        raise ValueError('Select a valid access role.')
    duplicate = conn.execute("SELECT 1 FROM access_requests WHERE employee_id=? AND access_role_id=? AND status IN ('PENDING_MANAGER','PENDING_IT','PROVISIONED')", (employee_id, access_role_id)).fetchone()
    if duplicate:
        raise ValueError('An active request for this access role already exists.')
    with transaction(conn):
        rid = _next_id(conn, 'access_requests', 'request_id', 'AR-EMP-')
        conn.execute("INSERT INTO access_requests(request_id,employee_id,access_role_id,business_justification,status,manager_decision,it_decision,created_at) VALUES(?,?,?,?,? ,NULL,NULL,?)", (rid, employee_id, access_role_id, justification, 'PENDING_MANAGER', _now()))
        event = _next_id(conn, 'audit_events', 'event_id', 'EVT-EMP-')
        append_audit(conn,event,actor['user_id'],'EMPLOYEE','ACCESS_REQUEST_SUBMITTED','AccessRequest',rid,None,'PENDING_MANAGER','Employee submitted access request',_now())
        conn.execute("INSERT INTO notifications(notification_id,recipient_user_id,recipient_role,type,entity_type,entity_id,message,created_at) VALUES(?,NULL,'MANAGER','ACCESS_REQUEST','AccessRequest',?,?,?)", (_next_id(conn,'notifications','notification_id','NTF-EMP-'),rid,f'Employee {employee_id} submitted an access request.',_now()))
    return rid


def acknowledge_asset(conn, employee_id, assignment_id, actor):
    row = conn.execute("SELECT * FROM asset_assignments WHERE assignment_id=? AND employee_id=?", (assignment_id, employee_id)).fetchone()
    if not row:
        raise ValueError('Equipment assignment not found for your account.')
    if row['status'] != 'DELIVERED':
        raise ValueError('Only delivered equipment can be acknowledged.')
    now = _now()
    with transaction(conn):
        conn.execute("UPDATE asset_assignments SET acknowledged_date=?,status='ACKNOWLEDGED' WHERE assignment_id=?", (now[:10], assignment_id))
        event = _next_id(conn,'audit_events','event_id','EVT-EMP-')
        append_audit(conn,event,actor['user_id'],'EMPLOYEE','ASSET_ACKNOWLEDGED','AssetAssignment',assignment_id,'DELIVERED','ACKNOWLEDGED','Employee confirmed receipt of equipment',now)
        conn.execute("INSERT INTO notifications(notification_id,recipient_user_id,recipient_role,type,entity_type,entity_id,message,created_at) VALUES(?,NULL,'IT','ASSET_ACKNOWLEDGED','AssetAssignment',?,?,?)", (_next_id(conn,'notifications','notification_id','NTF-EMP-'),assignment_id,f'Employee {employee_id} acknowledged equipment receipt.',now))
    return dict(conn.execute("SELECT * FROM asset_assignments WHERE assignment_id=?", (assignment_id,)).fetchone())


def complete_employee_task(conn, employee_id, task_id, actor):
    row = conn.execute("SELECT t.* FROM tasks t JOIN onboarding_cases c ON c.case_id=t.case_id WHERE t.task_id=? AND c.employee_id=?", (task_id, employee_id)).fetchone()
    if not row:
        raise ValueError('Task not found in your employee record.')
    if row['owner_team'].upper() not in ('EMPLOYEE','EMPLOYEE / HR','HR / EMPLOYEE'):
        raise ValueError('This task is not assigned to the employee.')
    return complete_task(conn, task_id, actor['user_id'], 'EMPLOYEE', _next_id(conn,'audit_events','event_id','EVT-EMP-'))


def mark_notifications_read(conn, user_id):
    conn.execute("UPDATE notifications SET is_read=1 WHERE recipient_user_id=?", (user_id,))
    conn.commit()
