from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from onboarding_sim.auth.security import hash_password
from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import hr
from onboarding_sim.web import main


@pytest.fixture()
def hr_database(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    generate(seed=20261022, scale="starter", out=out)
    db_path = out / "dataset.db"
    c = connect(db_path)
    c.execute(
        "INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) VALUES(?,?,?,?,?,?,?)",
        ("USR-HR-TEST", "EMP-000003", "hr.test@example.invalid", hash_password("StrongPass@2026"), "HR", "ACTIVE", "2026-10-22T08:00:00"),
    )
    c.execute(
        "INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) VALUES(?,?,?,?,?,?,?)",
        ("USR-MGR-TEST", "EMP-000002", "manager.test@example.invalid", hash_password("StrongPass@2026"), "MANAGER", "ACTIVE", "2026-10-22T08:00:00"),
    )
    c.commit()
    c.close()
    monkeypatch.setattr(main, "connect", lambda: connect(db_path))
    return db_path


def _new_employee_data(db_path):
    c = connect(db_path)
    role_id = c.execute("SELECT role_id FROM roles ORDER BY role_id LIMIT 1").fetchone()[0]
    manager_id = c.execute("SELECT employee_id FROM employees WHERE employment_status='ACTIVE' LIMIT 1").fetchone()[0]
    c.close()
    today = date.today()
    return {
        "full_name": "Build Three Test Employee",
        "work_email": "build3.employee@example.invalid",
        "worker_type": "EMPLOYEE",
        "role_id": role_id,
        "manager_id": manager_id,
        "hire_date": today.isoformat(),
        "start_date": (today + timedelta(days=7)).isoformat(),
        "contract_end_date": "",
        "location": "Hyderabad",
        "hr_notes": "HR portal integration test",
    }


def test_hr_create_employee_role_change_start_date_and_termination(hr_database):
    c = connect(hr_database)
    actor = {"user_id": "USR-HR-TEST", "app_role": "HR"}
    data = _new_employee_data(hr_database)
    created = hr.create_employee(c, data, actor)
    assert created["tasks_created"] == 12
    employee = c.execute("SELECT * FROM employees WHERE employee_id=?", (created["employee_id"],)).fetchone()
    assert employee["employment_status"] == "PRE_BOARDING"
    assert c.execute("SELECT COUNT(*) FROM tasks WHERE case_id=?", (created["case_id"],)).fetchone()[0] == 12

    another_role = c.execute("SELECT role_id FROM roles WHERE role_id!=? ORDER BY role_id LIMIT 1", (data["role_id"],)).fetchone()[0]
    changed = hr.change_employee_role(c, created["employee_id"], another_role, date.today().isoformat(), "Promotion approved", actor)
    assert changed["new_role_id"] == another_role

    new_start = (date.today() + timedelta(days=14)).isoformat()
    hr.change_start_date(c, created["employee_id"], new_start, "Joining date revised", actor)
    assert c.execute("SELECT start_date FROM employees WHERE employee_id=?", (created["employee_id"],)).fetchone()[0] == new_start
    assert c.execute("SELECT planned_start_date FROM onboarding_cases WHERE case_id=?", (created["case_id"],)).fetchone()[0] == new_start

    ended = hr.terminate_employee(c, created["employee_id"], date.today().isoformat(), "VOLUNTARY", "Employee resignation", actor)
    assert ended["tasks_created"] == 6
    assert c.execute("SELECT employment_status FROM employees WHERE employee_id=?", (created["employee_id"],)).fetchone()[0] == "TERMINATED"
    assert c.execute("SELECT COUNT(*) FROM tasks WHERE case_id=? AND case_type='OFFBOARDING'", (ended["offboarding_id"],)).fetchone()[0] == 6
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE entity_id=?", (created["employee_id"],)).fetchone()[0] == 4
    c.close()


def test_hr_service_rejects_bad_input_and_duplicate_email(hr_database):
    c = connect(hr_database)
    actor = {"user_id": "USR-HR-TEST", "app_role": "HR"}
    data = _new_employee_data(hr_database)
    bad = dict(data, start_date="not-a-date")
    with pytest.raises(ValueError, match="valid date"):
        hr.create_employee(c, bad, actor)
    created = hr.create_employee(c, data, actor)
    with pytest.raises(ValueError, match="already exists"):
        hr.create_employee(c, data, actor)
    with pytest.raises(ValueError, match="reason is required"):
        hr.change_employee_role(c, created["employee_id"], data["role_id"], date.today().isoformat(), "", actor)
    c.close()


def test_hr_web_portal_create_and_role_access(hr_database):
    client = TestClient(main.app)
    login = client.post("/login", data={"email": "hr.test@example.invalid", "password": "StrongPass@2026"}, follow_redirects=False)
    assert login.status_code == 303
    assert client.get("/hr/employees").status_code == 200
    assert client.get("/hr/employees/new").status_code == 200

    data = _new_employee_data(hr_database)
    response = client.post("/hr/employees", data=data, follow_redirects=False)
    assert response.status_code == 303
    employee_url = response.headers["location"]
    assert "/hr/employees/EMP-" in employee_url
    employee_id = employee_url.rsplit("/", 1)[-1].split("?", 1)[0]
    assert client.get(employee_url).status_code == 200
    assert client.get("/hr/employees?q=Build+Three").status_code == 200

    c = connect(hr_database)
    current_role = c.execute("SELECT role_id FROM employees WHERE employee_id=?", (employee_id,)).fetchone()[0]
    another_role = c.execute("SELECT role_id FROM roles WHERE role_id!=? LIMIT 1", (current_role,)).fetchone()[0]
    c.close()
    role_change = client.post(f"/hr/employees/{employee_id}/role", data={
        "role_id": another_role, "effective_date": date.today().isoformat(), "reason": "Approved internal move"
    }, follow_redirects=False)
    assert role_change.status_code == 303
    date_change = client.post(f"/hr/employees/{employee_id}/start-date", data={
        "new_start_date": (date.today() + timedelta(days=15)).isoformat(), "reason": "Business schedule update"
    }, follow_redirects=False)
    assert date_change.status_code == 303
    termination = client.post(f"/hr/employees/{employee_id}/terminate", data={
        "last_working_day": date.today().isoformat(), "termination_type": "VOLUNTARY", "reason": "Test exit"
    }, follow_redirects=False)
    assert termination.status_code == 303
    assert client.get(f"/hr/employees/{employee_id}").status_code == 200

    client.get("/logout")
    manager = client.post("/login", data={"email": "manager.test@example.invalid", "password": "StrongPass@2026"}, follow_redirects=False)
    assert manager.status_code == 303
    assert client.get("/hr/employees").status_code == 403
