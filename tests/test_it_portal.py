from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from onboarding_sim.auth.security import hash_password
from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import it
from onboarding_sim.web import main


@pytest.fixture()
def it_database(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    generate(seed=20261022, scale="starter", out=out)
    db_path = out / "dataset.db"
    c = connect(db_path)
    c.execute(
        "INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("USR-IT-BUILD5", "EMP-000004", "it.build5@example.invalid",
         hash_password("StrongPass@2026"), "IT", "ACTIVE", "2026-10-22T08:00:00"),
    )
    employee = c.execute(
        "SELECT employee_id FROM employees WHERE employee_id!='EMP-000004' AND employment_status='ACTIVE' "
        "ORDER BY employee_id LIMIT 1"
    ).fetchone()[0]
    c.execute("UPDATE employees SET start_date=? WHERE employee_id=?",
              ((date.today() - timedelta(days=2)).isoformat(), employee))
    access_role = c.execute("SELECT access_role_id FROM access_roles ORDER BY access_role_id LIMIT 1").fetchone()[0]
    c.execute(
        "INSERT INTO access_requests(request_id,employee_id,access_role_id,business_justification,status,manager_decision,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("AR-BUILD5-001", employee, access_role, "Approved for project duties",
         "PENDING_IT", "APPROVED", date.today().isoformat() + "T09:00:00"),
    )
    c.execute(
        "INSERT INTO approvals(approval_id,employee_id,request_type,approver_id,decision,reason,decided_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("APR-BUILD5-001", employee, "ACCESS", "EMP-MANAGER", "APPROVED",
         "Manager approved business need", date.today().isoformat() + "T09:00:00"),
    )
    asset = c.execute("SELECT asset_id FROM assets WHERE current_status='IN_STOCK' ORDER BY asset_id LIMIT 1").fetchone()[0]
    c.commit()
    c.close()
    monkeypatch.setattr(main, "connect", lambda: connect(db_path))
    return db_path, employee, asset


def _actor():
    return {"user_id": "USR-IT-BUILD5", "employee_id": "EMP-000004", "app_role": "IT"}


def test_it_provision_and_revoke_access(it_database):
    db_path, employee, _ = it_database
    c = connect(db_path)
    result = it.provision_access(c, "AR-BUILD5-001", _actor())
    assert result["status"] == "GRANTED"
    grant_id = result["grant_id"]
    assert c.execute("SELECT status FROM access_requests WHERE request_id='AR-BUILD5-001'").fetchone()[0] == "PROVISIONED"
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE entity_id=?", (grant_id,)).fetchone()[0] == 1
    with pytest.raises(ValueError, match="awaiting IT review"):
        it.provision_access(c, "AR-BUILD5-001", _actor())
    with pytest.raises(ValueError, match="reason"):
        it.revoke_access(c, grant_id, "", _actor())
    assert it.revoke_access(c, grant_id, "Employee no longer requires access", _actor())["status"] == "REVOKED"
    c.close()


def test_it_rejects_unapproved_or_future_access(it_database):
    db_path, employee, _ = it_database
    c = connect(db_path)
    c.execute("UPDATE access_requests SET status='PENDING_MANAGER',manager_decision=NULL WHERE request_id='AR-BUILD5-001'")
    c.commit()
    with pytest.raises(ValueError, match="manager-approved"):
        it.provision_access(c, "AR-BUILD5-001", _actor())
    c.execute("UPDATE access_requests SET status='PENDING_IT',manager_decision='APPROVED' WHERE request_id='AR-BUILD5-001'")
    c.execute("UPDATE employees SET start_date=? WHERE employee_id=?", ((date.today()+timedelta(days=5)).isoformat(), employee))
    c.commit()
    with pytest.raises(ValueError, match="before the employee start date"):
        it.provision_access(c, "AR-BUILD5-001", _actor())
    c.close()


def test_it_asset_assign_deliver_recover_and_reconcile(it_database):
    db_path, employee, asset = it_database
    c = connect(db_path)
    assigned = it.assign_asset(c, asset, employee, "Laptop for new starter", _actor())
    assignment_id = assigned["assignment_id"]
    assert assigned["status"] == "ASSIGNED"
    with pytest.raises(ValueError, match="not available"):
        it.assign_asset(c, asset, employee, "Duplicate attempt", _actor())
    assert it.mark_asset_delivered(c, assignment_id, _actor())["status"] == "DELIVERED"
    assert it.recover_asset(c, assignment_id, "Employee exit equipment return", _actor())["status"] == "RECOVERED"
    row = c.execute("SELECT current_status,current_holder_employee_id FROM assets WHERE asset_id=?", (asset,)).fetchone()
    assert row["current_status"] == "IN_STOCK"
    assert row["current_holder_employee_id"] is None
    assert all(x["assignment_id"] != assignment_id for x in it.reconcile_assets(c))
    with pytest.raises(ValueError, match="Only an active"):
        it.recover_asset(c, assignment_id, "Duplicate recovery", _actor())
    c.close()


def test_it_reject_access_and_role_scoped_routes(it_database):
    db_path, _, _ = it_database
    c = connect(db_path)
    result = it.reject_access(c, "AR-BUILD5-001", "Security policy does not permit this system role", _actor())
    assert result["status"] == "IT_REJECTED"
    c.close()

    client = TestClient(main.app)
    login = client.post("/login", data={
        "email": "it.build5@example.invalid", "password": "StrongPass@2026"
    }, follow_redirects=False)
    assert login.status_code == 303
    assert client.get("/it/access-requests").status_code == 200
    assert client.get("/it/grants").status_code == 200
    assert client.get("/it/assets").status_code == 200
    client.get("/logout", follow_redirects=False)
    assert client.get("/it/assets", follow_redirects=False).status_code == 303



def test_it_post_routes_complete_access_and_asset_actions(it_database):
    db_path, employee, asset = it_database
    client = TestClient(main.app)
    login = client.post("/login", data={
        "email": "it.build5@example.invalid", "password": "StrongPass@2026"
    }, follow_redirects=False)
    assert login.status_code == 303

    provision = client.post("/it/access-requests/AR-BUILD5-001/provision", follow_redirects=False)
    assert provision.status_code == 303
    c = connect(db_path)
    grant_id = c.execute("SELECT grant_id FROM access_grants WHERE employee_id=? ORDER BY grant_id DESC LIMIT 1", (employee,)).fetchone()[0]
    c.close()
    revoke = client.post(f"/it/grants/{grant_id}/revoke", data={"reason": "Access no longer required"}, follow_redirects=False)
    assert revoke.status_code == 303

    assign = client.post("/it/assets/assign", data={
        "asset_id": asset, "employee_id": employee, "reason": "Equipment for employee"
    }, follow_redirects=False)
    assert assign.status_code == 303
    c = connect(db_path)
    assignment_id = c.execute(
        "SELECT assignment_id FROM asset_assignments WHERE asset_id=? ORDER BY assignment_id DESC LIMIT 1",
        (asset,),
    ).fetchone()[0]
    c.close()
    delivered = client.post(f"/it/assets/{assignment_id}/deliver", follow_redirects=False)
    assert delivered.status_code == 303
    recovered = client.post(f"/it/assets/{assignment_id}/recover", data={
        "reason": "Returned after assignment ended"
    }, follow_redirects=False)
    assert recovered.status_code == 303

    client.get("/logout", follow_redirects=False)
    assert client.get("/it/grants", follow_redirects=False).status_code == 303


def test_it_reject_route_requires_reason_and_manager_cannot_open_it(it_database):
    client = TestClient(main.app)
    login = client.post("/login", data={
        "email": "it.build5@example.invalid", "password": "StrongPass@2026"
    }, follow_redirects=False)
    assert login.status_code == 303
    response = client.post("/it/access-requests/AR-BUILD5-001/reject", data={"reason": ""})
    assert response.status_code == 422
    client.get("/logout", follow_redirects=False)



def test_authenticated_pages_show_logout_and_logout_clears_actor_session(it_database):
    client = TestClient(main.app)
    login = client.post("/login", data={
        "email": "it.build5@example.invalid", "password": "StrongPass@2026"
    }, follow_redirects=False)
    assert login.status_code == 303

    dashboard = client.get("/portal/it")
    assert dashboard.status_code == 200
    assert 'href="/logout"' in dashboard.text
    assert ">Logout</a>" in dashboard.text
    assert "Switch actor" not in dashboard.text
    assert 'href="/portal/it"' in dashboard.text

    logout = client.get("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert client.get("/portal/it", follow_redirects=False).status_code == 303
