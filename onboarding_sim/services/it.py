"""IT and Operations access/asset lifecycle operations (Build 05)."""
from datetime import date, datetime, timezone
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


def _audit(conn, actor, action, entity_type, entity_id, old, new, reason, now):
    event_id = _next_id(conn, "audit_events", "event_id", "EVT-IT-", 8)
    append_audit(conn, event_id, actor["user_id"], "IT", action, entity_type, entity_id, old, new, reason, now)


def pending_provisioning(conn):
    return conn.execute(
        """SELECT ar.request_id,ar.employee_id,e.full_name,e.employment_status,e.start_date,
                  ar.access_role_id,ac.system_name,ac.privilege_level,ar.business_justification,
                  ar.status,ar.manager_decision
           FROM access_requests ar
           JOIN employees e ON e.employee_id=ar.employee_id
           JOIN access_roles ac ON ac.access_role_id=ar.access_role_id
           WHERE ar.status='PENDING_IT' AND ar.manager_decision='APPROVED'
           ORDER BY ar.created_at,ar.request_id"""
    ).fetchall()


def provision_access(conn, request_id, actor):
    row = conn.execute(
        """SELECT ar.*,e.employment_status,e.start_date,e.full_name,ac.requires_approval
           FROM access_requests ar JOIN employees e ON e.employee_id=ar.employee_id
           JOIN access_roles ac ON ac.access_role_id=ar.access_role_id
           WHERE ar.request_id=?""", (request_id,)
    ).fetchone()
    if not row:
        raise ValueError("Access request not found")
    if row["status"] != "PENDING_IT" or row["manager_decision"] != "APPROVED":
        raise ValueError("Only manager-approved requests awaiting IT review can be provisioned")
    if row["employment_status"] == "TERMINATED":
        raise ValueError("Cannot provision access to a terminated employee")
    if date.fromisoformat(row["start_date"]) > date.today():
        raise ValueError("Cannot provision access before the employee start date")
    if row["requires_approval"]:
        approved = conn.execute(
            """SELECT 1 FROM approvals WHERE employee_id=? AND request_type='ACCESS'
               AND decision='APPROVED' ORDER BY decided_at DESC LIMIT 1""", (row["employee_id"],)
        ).fetchone()
        if not approved:
            raise ValueError("Required manager approval record is missing")
    now = _now()
    grant_id = _next_id(conn, "access_grants", "grant_id", "GRANT-", 8)
    with transaction(conn):
        conn.execute(
            """INSERT INTO access_grants(grant_id,employee_id,access_role_id,requested_date,approved_date,
               granted_date,effective_from,status,granted_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (grant_id,row["employee_id"],row["access_role_id"],row["created_at"][:10],
             now[:10],now[:10],row["start_date"],"GRANTED",actor["user_id"])
        )
        conn.execute("UPDATE access_requests SET status='PROVISIONED',it_decision='PROVISIONED' WHERE request_id=?",(request_id,))
        _audit(conn,actor,"ACCESS_PROVISIONED","AccessGrant",grant_id,"PENDING_IT","GRANTED",
               f"Provisioned from approved request {request_id}",now)
        nid = _next_id(conn,"notifications","notification_id","NTF-",8)
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (nid,"HR","ACCESS_PROVISIONED","AccessGrant",grant_id,
             f"Access provisioned for {row['full_name']} ({row['employee_id']}).",now)
        )
    return {"grant_id":grant_id,"status":"GRANTED"}


def reject_access(conn, request_id, reason, actor):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A rejection reason is required")
    row = conn.execute("SELECT * FROM access_requests WHERE request_id=?",(request_id,)).fetchone()
    if not row:
        raise ValueError("Access request not found")
    if row["status"] != "PENDING_IT" or row["manager_decision"] != "APPROVED":
        raise ValueError("Only manager-approved requests awaiting IT review can be rejected")
    now = _now()
    with transaction(conn):
        conn.execute("UPDATE access_requests SET status='IT_REJECTED',it_decision='REJECTED' WHERE request_id=?",(request_id,))
        _audit(conn,actor,"ACCESS_REJECTED","AccessRequest",request_id,"PENDING_IT","IT_REJECTED",reason,now)
        nid=_next_id(conn,"notifications","notification_id","NTF-",8)
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (nid,"HR","ACCESS_IT_REJECTED","AccessRequest",request_id,f"IT rejected access request {request_id}: {reason}",now)
        )
    return {"request_id":request_id,"status":"IT_REJECTED"}


def list_grants(conn):
    return conn.execute(
        """SELECT g.grant_id,g.employee_id,e.full_name,ar.system_name,ar.privilege_level,
                  g.effective_from,g.effective_to,g.status,g.granted_date,g.revoked_date
           FROM access_grants g JOIN employees e ON e.employee_id=g.employee_id
           JOIN access_roles ar ON ar.access_role_id=g.access_role_id
           ORDER BY CASE WHEN g.status='GRANTED' THEN 0 ELSE 1 END,g.grant_id DESC LIMIT 500"""
    ).fetchall()


def revoke_access(conn, grant_id, reason, actor):
    reason=(reason or "").strip()
    if not reason:
        raise ValueError("A revocation reason is required")
    row=conn.execute("SELECT * FROM access_grants WHERE grant_id=?",(grant_id,)).fetchone()
    if not row:
        raise ValueError("Access grant not found")
    if row["status"] != "GRANTED":
        raise ValueError("Only an active grant can be revoked")
    now=_now()
    with transaction(conn):
        conn.execute("UPDATE access_grants SET status='REVOKED',revoked_date=? WHERE grant_id=?",(now[:10],grant_id))
        _audit(conn,actor,"ACCESS_REVOKED","AccessGrant",grant_id,"GRANTED","REVOKED",reason,now)
    return {"grant_id":grant_id,"status":"REVOKED"}


def asset_inventory(conn):
    return conn.execute(
        """SELECT asset_id,asset_type,serial_number,model,current_status,current_holder_employee_id
           FROM assets ORDER BY CASE current_status WHEN 'IN_STOCK' THEN 0 ELSE 1 END,asset_id LIMIT 500"""
    ).fetchall()


def assign_asset(conn, asset_id, employee_id, reason, actor):
    reason=(reason or "").strip()
    if not reason:
        raise ValueError("An assignment reason is required")
    asset=conn.execute("SELECT * FROM assets WHERE asset_id=?",(asset_id,)).fetchone()
    if not asset:
        raise ValueError("Asset not found")
    employee=conn.execute("SELECT * FROM employees WHERE employee_id=?",(employee_id,)).fetchone()
    if not employee:
        raise ValueError("Employee not found")
    if employee["employment_status"] == "TERMINATED":
        raise ValueError("Cannot assign an asset to a terminated employee")
    if asset["current_status"] != "IN_STOCK" or asset["current_holder_employee_id"]:
        raise ValueError("Asset is not available in stock")
    active=conn.execute(
        "SELECT 1 FROM asset_assignments WHERE asset_id=? AND status IN ('ASSIGNED','DELIVERED') LIMIT 1",(asset_id,)
    ).fetchone()
    if active:
        raise ValueError("Asset already has an active assignment")
    now=_now()
    assignment_id=_next_id(conn,"asset_assignments","assignment_id","ASG-",8)
    with transaction(conn):
        conn.execute(
            """INSERT INTO asset_assignments(assignment_id,asset_id,employee_id,assigned_date,status)
               VALUES(?,?,?,?, 'ASSIGNED')""",(assignment_id,asset_id,employee_id,now[:10])
        )
        conn.execute("UPDATE assets SET current_status='ASSIGNED',current_holder_employee_id=? WHERE asset_id=?",(employee_id,asset_id))
        _audit(conn,actor,"ASSET_ASSIGNED","AssetAssignment",assignment_id,"IN_STOCK","ASSIGNED",reason,now)
        nid=_next_id(conn,"notifications","notification_id","NTF-",8)
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (nid,"EMPLOYEE","ASSET_ASSIGNED","AssetAssignment",assignment_id,
             f"An asset ({asset['asset_type']} · {asset['serial_number']}) has been assigned to you.",now)
        )
    return {"assignment_id":assignment_id,"status":"ASSIGNED"}


def mark_asset_delivered(conn, assignment_id, actor):
    row=conn.execute(
        """SELECT aa.*,a.asset_id FROM asset_assignments aa JOIN assets a ON a.asset_id=aa.asset_id
           WHERE aa.assignment_id=?""",(assignment_id,)
    ).fetchone()
    if not row:
        raise ValueError("Asset assignment not found")
    if row["status"] != "ASSIGNED":
        raise ValueError("Only an assigned asset awaiting delivery can be marked delivered")
    now=_now()
    with transaction(conn):
        conn.execute("UPDATE asset_assignments SET status='DELIVERED',delivery_date=? WHERE assignment_id=?",(now[:10],assignment_id))
        _audit(conn,actor,"ASSET_DELIVERED","AssetAssignment",assignment_id,"ASSIGNED","DELIVERED","IT recorded physical delivery",now)
        nid=_next_id(conn,"notifications","notification_id","NTF-",8)
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (nid,"EMPLOYEE","ASSET_DELIVERED","AssetAssignment",assignment_id,
             f"Your assigned asset is marked delivered. Please acknowledge receipt.",now)
        )
    return {"assignment_id":assignment_id,"status":"DELIVERED"}


def recover_asset(conn, assignment_id, reason, actor):
    reason=(reason or "").strip()
    if not reason:
        raise ValueError("A recovery reason is required")
    row=conn.execute(
        """SELECT aa.*,a.current_status FROM asset_assignments aa JOIN assets a ON a.asset_id=aa.asset_id
           WHERE aa.assignment_id=?""",(assignment_id,)
    ).fetchone()
    if not row:
        raise ValueError("Asset assignment not found")
    if row["status"] not in ("ASSIGNED","DELIVERED","ACKNOWLEDGED"):
        raise ValueError("Only an active asset assignment can be recovered")
    now=_now()
    with transaction(conn):
        conn.execute("UPDATE asset_assignments SET status='RECOVERED',recovered_date=? WHERE assignment_id=?",(now[:10],assignment_id))
        conn.execute("UPDATE assets SET current_status='IN_STOCK',current_holder_employee_id=NULL WHERE asset_id=?",(row["asset_id"],))
        _audit(conn,actor,"ASSET_RECOVERED","AssetAssignment",assignment_id,row["status"],"RECOVERED",reason,now)
    return {"assignment_id":assignment_id,"status":"RECOVERED"}


def reconcile_assets(conn):
    """Return active assignment/asset-holder inconsistencies without mutating source records."""
    return conn.execute(
        """SELECT aa.assignment_id,aa.asset_id,aa.employee_id,aa.status,a.current_status,a.current_holder_employee_id
           FROM asset_assignments aa JOIN assets a ON a.asset_id=aa.asset_id
           WHERE (aa.status IN ('ASSIGNED','DELIVERED','ACKNOWLEDGED') AND
                    (a.current_status!='ASSIGNED' OR a.current_holder_employee_id!=aa.employee_id))
              OR (aa.status='RECOVERED' AND a.current_status='ASSIGNED'
                    AND a.current_holder_employee_id=aa.employee_id)
           ORDER BY aa.assignment_id"""
    ).fetchall()
