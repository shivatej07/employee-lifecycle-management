import pytest
from fastapi.testclient import TestClient
from onboarding_sim.auth.security import hash_password
from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import employee
from onboarding_sim.web import main


@pytest.fixture()
def employee_db(tmp_path, monkeypatch):
    out = tmp_path / 'exports'
    generate(seed=20261022, scale='starter', out=out)
    db = out / 'dataset.db'
    c = connect(db)
    emp = c.execute("SELECT e.employee_id FROM employees e JOIN onboarding_cases oc ON oc.employee_id=e.employee_id WHERE e.employment_status!='TERMINATED' ORDER BY e.employee_id LIMIT 1").fetchone()[0]
    c.execute("INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) VALUES(?,?,?,?,?,?,?)", ('USR-EMP-TEST', emp, 'employee.test@example.invalid', hash_password('StrongPass@2026'), 'EMPLOYEE', 'ACTIVE', '2026-10-22T08:00:00'))
    access_role = c.execute('SELECT access_role_id FROM access_roles ORDER BY access_role_id LIMIT 1').fetchone()[0]
    c.execute("INSERT INTO asset_assignments(assignment_id,asset_id,employee_id,assigned_date,delivery_date,status) SELECT 'ASG-EMP-TEST',asset_id,?,'2026-10-22','2026-10-22','DELIVERED' FROM assets WHERE current_status='IN_STOCK' ORDER BY asset_id LIMIT 1", (emp,))
    c.commit(); c.close()
    monkeypatch.setattr(main, 'connect', lambda: connect(db))
    return db, emp, access_role


def _login():
    client = TestClient(main.app)
    response = client.post('/login', data={'email':'employee.test@example.invalid','password':'StrongPass@2026'}, follow_redirects=False)
    assert response.status_code == 303
    return client


def test_employee_dashboard_and_employee_only_scope(employee_db):
    _, emp, _ = employee_db
    client = _login()
    response = client.get('/portal/employee')
    assert response.status_code == 200
    assert 'My onboarding tasks' in response.text
    assert 'My equipment' in response.text
    assert client.get('/hr/employees').status_code == 403
    assert client.get('/it/assets').status_code == 403


def test_employee_access_request_and_asset_acknowledgement(employee_db):
    db, emp, access_role = employee_db
    client = _login()
    response = client.post('/employee/access-requests', data={'access_role_id':access_role,'business_justification':'Required to complete assigned project responsibilities.'}, follow_redirects=False)
    assert response.status_code == 303
    c = connect(db)
    request = c.execute('SELECT * FROM access_requests WHERE employee_id=? ORDER BY created_at DESC LIMIT 1', (emp,)).fetchone()
    assert request['status'] == 'PENDING_MANAGER'
    c.close()
    ack = client.post('/employee/assets/ASG-EMP-TEST/acknowledge', follow_redirects=False)
    assert ack.status_code == 303
    c = connect(db)
    assignment = c.execute("SELECT status,acknowledged_date FROM asset_assignments WHERE assignment_id='ASG-EMP-TEST'").fetchone()
    assert assignment['status'] == 'ACKNOWLEDGED'
    assert assignment['acknowledged_date']
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE entity_id='ASG-EMP-TEST' AND action='ASSET_ACKNOWLEDGED'").fetchone()[0] == 1
    c.close()


def test_employee_cannot_acknowledge_another_employees_asset(employee_db):
    db, emp, _ = employee_db
    c = connect(db)
    other = c.execute("SELECT employee_id FROM employees WHERE employee_id!=? LIMIT 1", (emp,)).fetchone()[0]
    c.execute("UPDATE asset_assignments SET employee_id=? WHERE assignment_id='ASG-EMP-TEST'", (other,)); c.commit(); c.close()
    with pytest.raises(ValueError, match='not found for your account'):
        c = connect(db)
        try: employee.acknowledge_asset(c, emp, 'ASG-EMP-TEST', {'user_id':'USR-EMP-TEST'})
        finally: c.close()
