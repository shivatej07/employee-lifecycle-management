from fastapi.testclient import TestClient
from onboarding_sim.web.main import app

def test_all_demo_portals_and_role_gates():
    client=TestClient(app)
    cases=[
        ('employee.demo@example.invalid','/portal/employee','/portal/hr'),
        ('manager.demo@example.invalid','/portal/manager','/portal/it'),
        ('hr.demo@example.invalid','/portal/hr','/portal/admin'),
        ('it.demo@example.invalid','/portal/it','/portal/manager'),
        ('admin.demo@example.invalid','/portal/admin','/portal/hr'),
    ]
    for email,allowed,denied in cases:
        client=TestClient(app)
        r=client.post('/login',data={'email':email,'password':'Demo@2026!'},follow_redirects=False)
        assert r.status_code==303
        assert client.get(allowed).status_code==200
        assert client.get(denied).status_code==403

def test_login_rejects_wrong_password():
    client=TestClient(app)
    r=client.post('/login',data={'email':'admin.demo@example.invalid','password':'not-the-password'})
    assert r.status_code==200
    assert 'Unable to sign in' in r.text

def test_each_actor_dashboard_has_role_specific_workspace_and_correct_home_link():
    client_cases = [
        ('employee.demo@example.invalid', '/portal/employee', 'EMPLOYEE WORKSPACE', 'My onboarding tasks'),
        ('manager.demo@example.invalid', '/portal/manager', 'MANAGER WORKSPACE', 'Manager tools'),
        ('hr.demo@example.invalid', '/portal/hr', 'PEOPLE OPERATIONS', 'HR workspace'),
        ('it.demo@example.invalid', '/portal/it', 'IT & OPERATIONS', 'Operations workspace'),
        ('admin.demo@example.invalid', '/portal/admin', 'CONTROL CENTER', 'Platform management'),
    ]
    for email, path, marker, section in client_cases:
        client = TestClient(app)
        login_response = client.post('/login', data={'email': email, 'password': 'Demo@2026!'}, follow_redirects=False)
        assert login_response.status_code == 303
        page = client.get(path)
        assert page.status_code == 200
        assert marker in page.text
        assert section in page.text
        assert f'href="{path}"' in page.text
        assert 'Logout</a>' in page.text
        assert 'Logout / Switch actor' not in page.text
