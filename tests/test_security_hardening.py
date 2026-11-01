from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from onboarding_sim.web.main import app
from onboarding_sim.database import connect
from onboarding_sim.config import DB


def _client_login(email="employee.demo@example.invalid", password="Demo@2026!"):
    client = TestClient(app)
    return client, client.post("/login", data={"email": email, "password": password}, follow_redirects=False)


def test_successful_login_resets_failures_and_records_audit():
    c = connect()
    c.execute("UPDATE user_accounts SET failed_login_count=3, locked_until=NULL WHERE email='employee.demo@example.invalid'")
    c.commit()
    c.close()
    client, response = _client_login()
    assert response.status_code == 303
    c = connect()
    row = c.execute("SELECT failed_login_count,locked_until,last_login_at FROM user_accounts WHERE email='employee.demo@example.invalid'").fetchone()
    assert row["failed_login_count"] == 0
    assert row["locked_until"] is None
    assert row["last_login_at"]
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE action='LOGIN_SUCCESS' AND entity_id='employee.demo@example.invalid'").fetchone()[0] >= 1
    c.close()


def test_five_failed_logins_lock_account_for_fifteen_minutes():
    c = connect()
    c.execute("UPDATE user_accounts SET failed_login_count=0,locked_until=NULL WHERE email='employee.demo@example.invalid'")
    c.commit()
    c.close()
    client = TestClient(app)
    for _ in range(5):
        response = client.post("/login", data={"email":"employee.demo@example.invalid","password":"WrongPassword!123"}, follow_redirects=False)
    assert "locked for 15 minutes" in response.text
    c = connect()
    row = c.execute("SELECT failed_login_count,locked_until FROM user_accounts WHERE email='employee.demo@example.invalid'").fetchone()
    assert row["failed_login_count"] == 0
    assert row["locked_until"]
    c.close()


def test_locked_account_rejects_correct_password_until_expiry():
    c = connect()
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    c.execute("UPDATE user_accounts SET failed_login_count=0,locked_until=? WHERE email='employee.demo@example.invalid'",(future,))
    c.commit()
    c.close()
    client = TestClient(app)
    response = client.post("/login", data={"email":"employee.demo@example.invalid","password":"Demo@2026!"})
    assert "temporarily locked" in response.text
    c = connect()
    c.execute("UPDATE user_accounts SET locked_until=NULL WHERE email='employee.demo@example.invalid'")
    c.commit()
    c.close()
