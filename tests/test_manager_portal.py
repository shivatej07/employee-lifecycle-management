from fastapi.testclient import TestClient

from onboarding_sim.auth.security import hash_password
from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import manager
from onboarding_sim.web import main


def _manager_db(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    generate(seed=20261022, scale="starter", out=out)
    db_path = out / "dataset.db"
    c = connect(db_path)
    c.execute(
        "INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) VALUES(?,?,?,?,?,?,?)",
        ("USR-MGR-BUILD4", "EMP-000002", "manager.build4@example.invalid", hash_password("StrongPass@2026"), "MANAGER", "ACTIVE", "2026-10-22T08:00:00"),
    )
    employee = c.execute("SELECT employee_id FROM employees WHERE employee_id!='EMP-000002' AND employment_status='ACTIVE' ORDER BY employee_id LIMIT 1").fetchone()[0]
    c.execute("UPDATE employees SET manager_id='EMP-000002' WHERE employee_id=?", (employee,))
    access_role = c.execute("SELECT access_role_id FROM access_roles ORDER BY access_role_id LIMIT 1").fetchone()[0]
    c.execute(
        "INSERT INTO access_requests(request_id,employee_id,access_role_id,business_justification,status,created_at) VALUES(?,?,?,?,?,?)",
        ("AR-BUILD4-001", employee, access_role, "Required for assigned project work", "PENDING_MANAGER", "2026-10-22T09:00:00"),
    )
    c.commit()
    c.close()
    monkeypatch.setattr(main, "connect", lambda: connect(db_path))
    return db_path, employee


def test_manager_team_and_readiness_are_scoped(tmp_path, monkeypatch):
    db_path, employee_id = _manager_db(tmp_path, monkeypatch)
    c = connect(db_path)
    rows = manager.team_overview(c, "EMP-000002")
    assert rows
    assert any(row["employee_id"] == employee_id for row in rows)
    assert all(row["employee_id"] != "EMP-000002" for row in rows)
    tasks = manager.team_tasks(c, "EMP-000002")
    assert tasks
    assert all(row["employee_id"] == employee_id or row["employee_id"] in {x["employee_id"] for x in rows} for row in tasks)
    c.close()


def test_manager_access_approval_rejection_and_scope(tmp_path, monkeypatch):
    db_path, employee_id = _manager_db(tmp_path, monkeypatch)
    c = connect(db_path)
    actor = {"user_id": "USR-MGR-BUILD4", "employee_id": "EMP-000002", "app_role": "MANAGER"}
    result = manager.decide_access_request(c, "AR-BUILD4-001", "APPROVE", "Approved for current project", actor)
    assert result["status"] == "PENDING_IT"
    assert c.execute("SELECT manager_decision FROM access_requests WHERE request_id='AR-BUILD4-001'").fetchone()[0] == "APPROVED"
    assert c.execute("SELECT COUNT(*) FROM approvals WHERE employee_id=? AND decision='APPROVED'", (employee_id,)).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM notifications WHERE recipient_role='IT' AND entity_id='AR-BUILD4-001'").fetchone()[0] == 1
    try:
        manager.decide_access_request(c, "AR-BUILD4-001", "REJECT", "Late second decision", actor)
        assert False, "A completed manager decision must not be overwritten"
    except ValueError as exc:
        assert "already been decided" in str(exc)
    c.close()


def test_manager_routes_and_role_gates(tmp_path, monkeypatch):
    _manager_db(tmp_path, monkeypatch)
    client = TestClient(main.app)
    login = client.post("/login", data={"email": "manager.build4@example.invalid", "password": "StrongPass@2026"}, follow_redirects=False)
    assert login.status_code == 303
    assert client.get("/manager/team").status_code == 200
    assert client.get("/manager/access-requests").status_code == 200
    assert client.get("/manager/tasks").status_code == 200
    decision = client.post("/manager/access-requests/AR-BUILD4-001/decision", data={"decision": "REVERIFY", "reason": "Please confirm business need"}, follow_redirects=False)
    assert decision.status_code == 303
    client.get("/logout", follow_redirects=False)
    assert client.get("/manager/team", follow_redirects=False).status_code == 303
