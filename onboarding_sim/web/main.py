from fastapi import FastAPI,Request,Form,File,UploadFile,HTTPException
from html import escape
from datetime import datetime, timezone, timedelta
from fastapi.responses import HTMLResponse,RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from onboarding_sim.config import ROOT,DB,SECRET
from onboarding_sim.database import connect
from onboarding_sim.auth.security import hash_password,verify_password,validate_password
from onboarding_sim.authz import PORTAL_PATHS
from onboarding_sim.search import search
from onboarding_sim.services import hr as hr_service
from onboarding_sim.services import offboarding as offboarding_service
from onboarding_sim.services import manager as manager_service
from onboarding_sim.services import it as it_service
from onboarding_sim.services import employee as employee_service
from onboarding_sim.services import documents as document_service
app=FastAPI(title='Employee Lifecycle Management System')
app.add_middleware(
    SessionMiddleware, secret_key=SECRET, same_site='lax',
    https_only=False, max_age=1800, path="/"
)
app.mount('/static',StaticFiles(directory=ROOT/'onboarding_sim/web/static'),name='static')
SESSION_IDLE_SECONDS = 1800
LOGIN_LOCK_MINUTES = 15
LOGIN_MAX_FAILURES = 5

def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)

def _auth_event(conn, actor_id, actor_role, action, email, reason):
    row = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    event_id = f"EVT-AUTH-{row[0]+1:08d}"
    conn.execute(
        "INSERT INTO audit_events(event_id,event_ts,actor_id,actor_role,action,entity_type,entity_id,from_state,to_state,reason,override_flag) VALUES(?,?,?,?,?,?,?,?,?,?,0)",
        (event_id, _utcnow().isoformat(), actor_id, actor_role, action, "UserAccount", email, None, None, reason)
    )

def actor(req):
    user = req.session.get('user')
    if not user:
        return None
    now = _utcnow()
    last = req.session.get("last_activity")
    try:
        previous = datetime.fromisoformat(last) if last else now
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        previous = now
    if (now - previous).total_seconds() > SESSION_IDLE_SECONDS:
        req.session.clear()
        return None
    req.session["last_activity"] = now.isoformat()
    return user
def render(title,body,user=None):
    user = user or {}
    who = user.get('email', '')
    role = user.get('app_role', '')
    dashboard = PORTAL_PATHS.get(role, '/')
    nav = (
        f'<nav class="top-nav"><a href="{dashboard}">My dashboard</a>'
        f'<span class="nav-role">{escape(role.replace("_", " ").title())}</span>'
        '<a class="logout-link" href="/logout">Logout</a></nav>'
    ) if who else ''
    page_class = 'auth-page' if title.lower() in ('sign in', 'create account', 'registration') else 'app-page'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        f'<meta name="theme-color" content="#10233f">'
        f'<title>{escape(title)} · Lifecycle OS</title><link rel="stylesheet" href="/static/app.css"></head>'
        f'<body class="{page_class}"><header><a class="brand" href="/"><b>LIFECYCLE OS</b></a><span>{escape(who)}</span></header>{nav}'
        f'<main><h1>{escape(title)}</h1><div class="page-content">{body}</div></main>'
        f'</body></html>'
    )
@app.get('/',response_class=HTMLResponse)
def home(req:Request):
    u=actor(req);return RedirectResponse(PORTAL_PATHS[u['app_role']] if u else '/login',303)
@app.get('/login',response_class=HTMLResponse)
def login_page():return render('Sign in','<form method="post"><label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label><button>Sign in</button><a href="/register">Create account</a></form>')
@app.post('/login',response_class=HTMLResponse)
def login(req:Request,email:str=Form(...),password:str=Form(...)):
    normalized = email.lower().strip()
    c=connect()
    r=c.execute('SELECT * FROM user_accounts WHERE email=?',(normalized,)).fetchone()
    now=_utcnow()
    if not r or r['account_status']!='ACTIVE':
        if r:
            _auth_event(c, r['user_id'], r['app_role'], 'LOGIN_FAILURE', normalized, 'Inactive account or invalid credentials')
            c.commit()
        c.close()
        return render('Sign in','<p class="error">Unable to sign in. Check details or account status.</p><a href="/login">Try again</a>')
    locked_until = r['locked_until']
    if locked_until:
        try:
            lock_time = datetime.fromisoformat(locked_until)
            if lock_time.tzinfo is None:
                lock_time = lock_time.replace(tzinfo=timezone.utc)
        except ValueError:
            lock_time = now
        if lock_time > now:
            remaining = max(1, int((lock_time-now).total_seconds()//60)+1)
            c.close()
            return render('Sign in',f'<p class="error">Account temporarily locked. Try again in about {remaining} minute(s).</p><a href="/login">Return</a>')
    if not verify_password(r['password_hash'],password):
        failures = r['failed_login_count'] + 1
        lock = (now + timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat() if failures >= LOGIN_MAX_FAILURES else None
        c.execute('UPDATE user_accounts SET failed_login_count=?,locked_until=? WHERE user_id=?',(0 if lock else failures,lock,r['user_id']))
        _auth_event(c, r['user_id'], r['app_role'], 'LOGIN_FAILURE', normalized,
                    f'Invalid password; consecutive failures={failures}' + ('; account locked for 15 minutes' if lock else ''))
        c.commit(); c.close()
        if lock:
            return render('Sign in','<p class="error">Too many failed attempts. Account locked for 15 minutes.</p><a href="/login">Return</a>')
        return render('Sign in','<p class="error">Unable to sign in. Check details or account status.</p><a href="/login">Try again</a>')
    c.execute('UPDATE user_accounts SET failed_login_count=0,locked_until=NULL,last_login_at=? WHERE user_id=?',(now.isoformat(),r['user_id']))
    _auth_event(c, r['user_id'], r['app_role'], 'LOGIN_SUCCESS', normalized, 'Successful authentication')
    c.commit()
    req.session.clear()
    req.session['user']={'user_id':r['user_id'],'employee_id':r['employee_id'],'email':r['email'],'app_role':r['app_role']}
    req.session['last_activity']=now.isoformat()
    c.close()
    return RedirectResponse(PORTAL_PATHS[r['app_role']],303)
@app.get('/register',response_class=HTMLResponse)
def register_page():return render('Create account','<form method="post"><label>Employee ID<input name="employee_id" required></label><label>Company email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label><button>Create account</button></form>')
@app.post('/register',response_class=HTMLResponse)
def register(employee_id:str=Form(...),email:str=Form(...),password:str=Form(...)):
    c=connect();e=c.execute('SELECT * FROM employees WHERE employee_id=? AND work_email=?',(employee_id,email.lower().strip())).fetchone()
    if not e:c.close();return render('Registration','<p class="error">Identity could not be verified.</p>')
    if not validate_password(password,email):c.close();return render('Registration','<p class="error">Password does not meet policy.</p>')
    if c.execute('SELECT 1 FROM user_accounts WHERE employee_id=? OR email=?',(employee_id,email.lower().strip())).fetchone():c.close();return render('Registration','<p class="error">Account already exists.</p>')
    uid=f"USR-{c.execute('SELECT COUNT(*) FROM user_accounts').fetchone()[0]+1:06d}"
    c.execute('INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at) VALUES(?,?,?,?,?,?,?)',(uid,employee_id,email.lower().strip(),hash_password(password),'EMPLOYEE','ACTIVE','2026-10-22T12:00:00'))
    c.commit();c.close();return render('Registration complete','<p>Account created. <a href="/login">Sign in</a>.</p>')
@app.get('/logout')
def logout(req:Request):req.session.clear();return RedirectResponse('/login',303)
def _admin_dashboard(conn):
    metrics = [
        ("Employees", "employees", "fa-users"),
        ("User accounts", "user_accounts", "fa-user-shield"),
        ("Open tasks", "tasks", "fa-list-check", "status NOT IN (\'DONE\',\'CANCELLED\')"),
        ("Active access grants", "access_grants", "fa-key", "status = 'ACTIVE'"),
        ("Assets", "assets", "fa-laptop"),
        ("Open exceptions", "exception_records", "fa-triangle-exclamation", "status NOT IN (\'RESOLVED\',\'CLOSED\')"),
    ]
    cards=[]
    for item in metrics:
        label, table, icon = item[:3]
        where = item[3] if len(item)>3 else None
        count = conn.execute(f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")).fetchone()[0]
        cards.append(f'<article class="metric-card"><span class="metric-label">{escape(label)}</span><strong>{count:,}</strong><small>Current records</small></article>')
    recent = conn.execute("SELECT event_ts,actor_role,action,entity_type,entity_id,reason FROM audit_events ORDER BY event_ts DESC LIMIT 8").fetchall()
    audit_rows=''.join(f'<tr><td>{escape(x["event_ts"])}</td><td>{escape(x["actor_role"])}</td><td>{escape(x["action"])}</td><td>{escape(x["entity_type"])} · {escape(x["entity_id"])}</td></tr>' for x in recent) or '<tr><td colspan="4">No audit activity recorded.</td></tr>'
    return ('<div class="admin-welcome"><div><p class="eyebrow">CONTROL CENTER</p><h2>System overview</h2><p>Monitor workforce lifecycle operations, access governance and platform activity from one place.</p></div><a class="button-link" href="/admin/health">View system health</a></div>'
      '<div class="stats-grid admin-metrics">'+''.join(cards)+'</div>'
      '<div class="admin-grid"><section class="admin-panel"><div class="section-heading"><div><p class="eyebrow">ADMINISTRATION</p><h2>Platform management</h2></div></div><div class="admin-link-grid">'
      '<a class="admin-link-card" href="/admin/accounts"><span class="admin-icon">UA</span><b>User accounts</b><small>Roles, access status and sign-in history</small></a>'
      '<a class="admin-link-card" href="/admin/audit"><span class="admin-icon">AL</span><b>Audit trail</b><small>Trace actions and lifecycle decisions</small></a>'
      '<a class="admin-link-card" href="/admin/exceptions"><span class="admin-icon">EX</span><b>Workflow exceptions</b><small>Review operational issues and severity</small></a>'
      '<a class="admin-link-card" href="/admin/reconciliation"><span class="admin-icon">RC</span><b>Reconciliation</b><small>Inspect data consistency checks</small></a>'
      '<a class="admin-link-card" href="/admin/health"><span class="admin-icon">SH</span><b>System health</b><small>Database record counts and platform status</small></a>'
      '<a class="admin-link-card" href="/search"><span class="admin-icon">GS</span><b>Global search</b><small>Find employee records across the system</small></a>'
      '</div></section><section class="admin-panel"><div class="section-heading"><div><p class="eyebrow">TRACEABILITY</p><h2>Recent audit activity</h2></div><a href="/admin/audit">View all</a></div><div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Entity</th></tr></thead><tbody>'+audit_rows+'</tbody></table></div></section></div>')

@app.get('/portal/{role}',response_class=HTMLResponse)
def portal(req:Request,role:str):
    u=actor(req)
    if not u:return RedirectResponse('/login',303)
    mapping={'employee':'EMPLOYEE','manager':'MANAGER','hr':'HR','it':'IT','admin':'SYSADMIN'}
    if mapping.get(role)!=u['app_role']:raise HTTPException(403,'Access denied')
    c=connect();r=u['app_role']
    if r=='EMPLOYEE':
        if not u.get('employee_id'):
            c.close(); raise HTTPException(403, 'Employee account is not linked to an employee record')
        e, tasks, assets, notices, requests = employee_service.dashboard_data(c, u['employee_id'], u['user_id'])
        pending_tasks = sum(1 for x in tasks if x['status'] not in ('DONE','CANCELLED'))
        unread = sum(1 for x in notices if not x['is_read'])
        task_rows = ''.join(
            f'<tr><td>{escape(x["title"])}</td><td>{escape(x["owner_team"])}</td><td>{escape(x["due_date"])}</td><td>{escape(x["status"])}</td>'
            + (f'<td><form method="post" action="/employee/tasks/{escape(x["task_id"])}/complete"><button>Complete</button></form></td>' if x['status'] in ('READY','IN_PROGRESS') and x['owner_team'].upper() in ('EMPLOYEE','EMPLOYEE / HR','HR / EMPLOYEE') else '<td>—</td>') + '</tr>' for x in tasks
        ) or '<tr><td colspan="5">No onboarding tasks are linked to your profile yet.</td></tr>'
        asset_rows = ''.join(
            f'<tr><td>{escape(x["asset_type"])} · {escape(x["model"])}</td><td>{escape(x["serial_number"])}</td><td>{escape(x["status"])}</td><td>'
            + (f'<form method="post" action="/employee/assets/{escape(x["assignment_id"])}/acknowledge"><button>Confirm receipt</button></form>' if x['status']=='DELIVERED' else 'Confirmed' if x['status']=='ACKNOWLEDGED' else '—') + '</td></tr>' for x in assets
        ) or '<tr><td colspan="4">No equipment assigned.</td></tr>'
        notice_rows = ''.join(f'<li><b>{escape(x["type"])}</b> · {escape(x["message"])} <small>{escape(x["created_at"])}</small></li>' for x in notices) or '<li>No notifications.</li>'
        documents = document_service.list_employee_documents(c, u['employee_id'])
        document_rows = ''.join(
            f'<tr><td>{escape(d["document_type"])}</td><td>{escape(d["original_filename"])}</td><td>{escape(d["status"])}</td><td>{escape(d["review_note"] or "Awaiting HR review")}</td></tr>'
            for d in documents
        ) or '<tr><td colspan="4">No documents uploaded yet.</td></tr>'
        request_rows = ''.join(f'<li>{escape(x["system_name"])} · {escape(x["status"])} — {escape(x["business_justification"])}</li>' for x in requests) or '<li>No access requests submitted.</li>'
        access_roles = c.execute('SELECT access_role_id,system_name,privilege_level FROM access_roles ORDER BY system_name').fetchall()
        role_options = ''.join(f'<option value="{escape(x["access_role_id"])}">{escape(x["system_name"])} · {escape(x["privilege_level"])}</option>' for x in access_roles)
        flash_message = req.session.pop('flash_message', None)
        flash_html = f'<div class="notice">{escape(flash_message)}</div>' if flash_message else ''
        body = (flash_html + f'<div class="dashboard-hero employee-hero"><div><p class="eyebrow">EMPLOYEE WORKSPACE</p><h2>Welcome back, {escape(e["full_name"])}</h2><p>Your onboarding, equipment, access and documents in one place.</p><span class="hero-meta">{escape(e["employee_id"])} · {escape(e["employment_status"])}</span></div><div class="hero-mark">MY<br>WORK</div></div>'
                f'<div class="stats-grid"><article><h3>{pending_tasks}</h3><p>Open tasks</p></article><article><h3>{len(assets)}</h3><p>Equipment records</p></article><article><h3>{unread}</h3><p>Unread notifications</p></article></div>'
                '<section><h2>My onboarding tasks</h2><div class="table-wrap"><table><thead><tr><th>Task</th><th>Owner</th><th>Due</th><th>Status</th><th>Action</th></tr></thead><tbody>'+task_rows+'</tbody></table></div></section>'
                '<section><h2>My equipment</h2><div class="table-wrap"><table><thead><tr><th>Equipment</th><th>Serial</th><th>Status</th><th>Action</th></tr></thead><tbody>'+asset_rows+'</tbody></table></div></section>'
                '<section><h2>Request system access</h2><form method="post" action="/employee/access-requests"><label>Access role<select name="access_role_id" required>'+role_options+'</select></label><label>Business justification<textarea name="business_justification" minlength="12" required></textarea></label><button>Submit access request</button></form></section>'
                '<section><h2>My access requests</h2><ul>'+request_rows+'</ul></section>'
                '<section><h2>My documents</h2><form method="post" enctype="multipart/form-data" action="/employee/documents">'
                '<label>Document category<select name="document_type" required><option value="IDENTITY">Identity</option><option value="ADDRESS">Address</option><option value="EDUCATION">Education</option><option value="TAX">Tax</option><option value="CONTRACT">Contract</option><option value="OTHER">Other</option></select></label>'
                '<label>Select file (PDF, PNG, JPG, JPEG, DOCX; max 5 MB)<input type="file" name="upload" accept=".pdf,.png,.jpg,.jpeg,.docx" required></label><button>Upload document</button></form>'
                '<div class="table-wrap"><table><thead><tr><th>Category</th><th>File</th><th>Status</th><th>HR review</th></tr></thead><tbody>'+document_rows+'</tbody></table></div></section>'
                '<section><h2>Notifications</h2><form method="post" action="/employee/notifications/read"><button class="secondary">Mark my notifications as read</button></form><ul>'+notice_rows+'</ul></section>')
    elif r=='MANAGER':
        rows=manager_service.team_overview(c,u['employee_id'])
        pending=len(manager_service.pending_access_requests(c,u['employee_id']))
        task_count=c.execute("SELECT COUNT(*) FROM tasks t JOIN onboarding_cases oc ON oc.case_id=t.case_id JOIN employees e ON e.employee_id=oc.employee_id WHERE e.manager_id=? AND t.status NOT IN ('DONE','CANCELLED')",(u['employee_id'],)).fetchone()[0]
        cards = ''.join(f'<div class="team-mini-card"><span class="avatar-chip">{escape(x["full_name"][:1].upper())}</span><div><b>{escape(x["full_name"])}</b><small>{escape(x["employee_id"])} · {escape(x["employment_status"])}</small></div><strong>{x["readiness_percent"]}%</strong></div>' for x in rows[:6]) or '<p class="empty-state">No direct reports are assigned yet.</p>'
        body=(f'<div class="dashboard-hero"><div><p class="eyebrow">MANAGER WORKSPACE</p><h2>Lead your team with clarity.</h2><p>Track onboarding progress, review access requests and keep handovers moving.</p></div><div class="hero-mark">TEAM<br>HUB</div></div>'
              f'<div class="stats-grid"><article class="metric-card"><span class="metric-label">Direct reports</span><strong>{len(rows):,}</strong><small>Employees in your team</small></article><article class="metric-card"><span class="metric-label">Access approvals</span><strong>{pending:,}</strong><small>Awaiting your review</small></article><article class="metric-card"><span class="metric-label">Open tasks</span><strong>{task_count:,}</strong><small>Team onboarding tasks</small></article></div>'
              '<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">QUICK ACTIONS</p><h2>Manager tools</h2></div></div><div class="dashboard-actions">'
              '<a class="dashboard-action" href="/manager/team"><span>01</span><b>My team</b><small>View employee profiles and readiness</small></a>'
              '<a class="dashboard-action" href="/manager/access-requests"><span>02</span><b>Access approvals</b><small>Review and decide access requests</small></a>'
              '<a class="dashboard-action" href="/manager/tasks"><span>03</span><b>Onboarding tasks</b><small>Monitor assigned team tasks</small></a>'
              '<a class="dashboard-action" href="/manager/offboarding"><span>04</span><b>Offboarding handovers</b><small>Coordinate employee transitions</small></a></div></section>'
              '<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">TEAM SNAPSHOT</p><h2>Employee readiness</h2></div><a href="/manager/team">View team</a></div><div class="team-mini-grid">'+cards+'</div></section>')
    elif r=='HR':
        rows=c.execute('SELECT employment_status,COUNT(*) n FROM employees GROUP BY employment_status').fetchall()
        counts={x['employment_status']:x['n'] for x in rows}
        total=c.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
        pre=counts.get('PRE_BOARDING',0); active=counts.get('ACTIVE',0); terminated=counts.get('TERMINATED',0)
        docs=c.execute("SELECT COUNT(*) FROM employee_documents WHERE status='PENDING'").fetchone()[0]
        offboarding=c.execute("SELECT COUNT(*) FROM offboarding_cases WHERE status NOT IN ('CLOSED','COMPLETED')").fetchone()[0]
        body=(f'<div class="dashboard-hero"><div><p class="eyebrow">PEOPLE OPERATIONS</p><h2>Build a better employee experience.</h2><p>Manage the workforce lifecycle from preboarding through offboarding with a clear view of people and pending actions.</p></div><div class="hero-mark">PEOPLE<br>FIRST</div></div>'
              f'<div class="stats-grid"><article class="metric-card"><span class="metric-label">Total employees</span><strong>{total:,}</strong><small>Across all employment states</small></article><article class="metric-card"><span class="metric-label">Active</span><strong>{active:,}</strong><small>Currently employed</small></article><article class="metric-card"><span class="metric-label">Preboarding</span><strong>{pre:,}</strong><small>Preparing to join</small></article><article class="metric-card"><span class="metric-label">Pending documents</span><strong>{docs:,}</strong><small>Awaiting HR verification</small></article><article class="metric-card"><span class="metric-label">Open offboarding</span><strong>{offboarding:,}</strong><small>Cases needing coordination</small></article></div>'
              '<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">QUICK ACTIONS</p><h2>HR workspace</h2></div></div><div class="dashboard-actions">'
              '<a class="dashboard-action" href="/hr/employees"><span>01</span><b>Employee directory</b><small>Search and manage employee records</small></a>'
              '<a class="dashboard-action" href="/hr/employees/new"><span>02</span><b>Create employee</b><small>Start a new employee lifecycle record</small></a>'
              '<a class="dashboard-action" href="/hr/documents"><span>03</span><b>Document verification</b><small>Review submitted employee documents</small></a>'
              '<a class="dashboard-action" href="/hr/offboarding"><span>04</span><b>Offboarding cases</b><small>Track exits and closure requirements</small></a></div></section>'
              f'<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">WORKFORCE OVERVIEW</p><h2>Employment status</h2></div></div><div class="status-summary"><div><b>{active:,}</b><span>Active</span></div><div><b>{pre:,}</b><span>Preboarding</span></div><div><b>{terminated:,}</b><span>Terminated</span></div></div></section>')
    elif r=='IT':
        rows=c.execute('SELECT status,COUNT(*) n FROM access_grants GROUP BY status').fetchall()
        grant_counts={x['status']:x['n'] for x in rows}
        pending_it=c.execute("SELECT COUNT(*) FROM access_requests WHERE status='PENDING_IT'").fetchone()[0]
        pending_manager=c.execute("SELECT COUNT(*) FROM access_requests WHERE status='PENDING_MANAGER'").fetchone()[0]
        stock=c.execute("SELECT COUNT(*) FROM assets WHERE current_status='IN_STOCK'").fetchone()[0]
        active_grants=grant_counts.get('GRANTED',grant_counts.get('ACTIVE',0))
        body=(f'<div class="dashboard-hero"><div><p class="eyebrow">IT & OPERATIONS</p><h2>Keep access and assets under control.</h2><p>Provision approved access, maintain equipment inventory and support secure employee transitions.</p></div><div class="hero-mark">SECURE<br>OPS</div></div>'
              f'<div class="stats-grid"><article class="metric-card"><span class="metric-label">IT provisioning queue</span><strong>{pending_it:,}</strong><small>Approved requests awaiting action</small></article><article class="metric-card"><span class="metric-label">Active grants</span><strong>{active_grants:,}</strong><small>Current access assignments</small></article><article class="metric-card"><span class="metric-label">Assets in stock</span><strong>{stock:,}</strong><small>Available equipment inventory</small></article><article class="metric-card"><span class="metric-label">Manager review</span><strong>{pending_manager:,}</strong><small>Requests awaiting manager decision</small></article></div>'
              '<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">QUICK ACTIONS</p><h2>Operations workspace</h2></div></div><div class="dashboard-actions">'
              f'<a class="dashboard-action" href="/it/access-requests"><span>01</span><b>Provisioning queue</b><small>{pending_it:,} requests ready for IT review</small></a>'
              '<a class="dashboard-action" href="/it/grants"><span>02</span><b>Manage access grants</b><small>Review, provision and revoke access</small></a>'
              '<a class="dashboard-action" href="/it/assets"><span>03</span><b>Asset operations</b><small>Manage inventory and assignments</small></a>'
              '<a class="dashboard-action" href="/it/offboarding"><span>04</span><b>Offboarding queue</b><small>Recover assets and revoke access</small></a></div></section>'
              '<section class="dashboard-section"><div class="section-heading"><div><p class="eyebrow">ACCESS GOVERNANCE</p><h2>Grant status</h2></div></div><div class="status-summary">'+''.join(f'<div><b>{x["n"]:,}</b><span>{escape(x["status"].replace("_"," ").title())}</span></div>' for x in rows)+'</div></section>')
    else:
        body = _admin_dashboard(c)
    c.close();return render(r+' Portal',body,u)
@app.get('/admin/health',response_class=HTMLResponse)
def health(req:Request):
    u=actor(req)
    if not u or u['app_role']!='SYSADMIN':
        raise HTTPException(403,'Access denied')

    c = connect()
    tables = (
        ('employees', 'Employees', 'People records currently stored in the platform'),
        ('tasks', 'Tasks', 'Lifecycle tasks across onboarding and offboarding'),
        ('access_grants', 'Access grants', 'Provisioned and tracked access assignments'),
        ('assets', 'Assets', 'Equipment and inventory records'),
    )
    metric_cards = []
    for table, label, description in tables:
        count = c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        metric_cards.append(
            f'<article class="metric-card health-metric"><span class="metric-label">{escape(label)}</span>'
            f'<strong>{count:,}</strong><small>{escape(description)}</small></article>'
        )

    # A successful query against the required tables confirms the app can read its core data.
    db_status = 'Operational'
    db_detail = 'Database connection and core record queries are responding.'
    c.close()
    body = (
        '<section class="health-hero"><div><p class="eyebrow">PLATFORM MONITORING</p>'
        '<h2>System health at a glance</h2>'
        '<p>Monitor the core data services that power employee lifecycle operations.</p></div>'
        '<div class="health-status"><span class="health-status-dot"></span><div><b>All systems operational</b>'
        '<small>Core database checks passed</small></div></div></section>'
        '<section class="health-section"><div class="section-heading"><div><p class="eyebrow">DATA OVERVIEW</p>'
        '<h2>Platform records</h2></div><span class="health-updated">Live database counts</span></div>'
        '<div class="stats-grid health-metrics">' + ''.join(metric_cards) + '</div></section>'
        '<section class="health-section"><div class="section-heading"><div><p class="eyebrow">SERVICE STATUS</p>'
        '<h2>Core components</h2></div></div><div class="health-components">'
        '<article class="health-component"><span class="health-component-icon">DB</span><div><b>Database</b>'
        f'<small>{escape(db_detail)}</small></div><span class="health-pill">{escape(db_status)}</span></article>'
        '<article class="health-component"><span class="health-component-icon">API</span><div><b>Application</b>'
        '<small>Lifecycle OS web application is serving this admin page.</small></div><span class="health-pill">Operational</span></article>'
        '<article class="health-component"><span class="health-component-icon">AU</span><div><b>Admin access</b>'
        '<small>System health is available to authenticated system administrators.</small></div><span class="health-pill">Protected</span></article>'
        '</div></section>'
        '<a class="health-back-link" href="/portal/admin">← Back to admin dashboard</a>'
    )
    return render('System health',body,u)
@app.get('/search',response_class=HTMLResponse)
def search_page(req:Request,q:str=''):
    u=actor(req)
    if not u:return RedirectResponse('/login',303)
    c=connect();rows=search(c,u,q);c.close()
    body='<form><input name="q" placeholder="Search employees" value="'+q.replace('"','')+'"><button>Search</button></form><ul>'+''.join(f'<li>{x["id"]} — {x["label"]}</li>' for x in rows)+'</ul>'
    return render('Search',body,u)


# Build 03: HR employee lifecycle workspace
def _hr_actor(req):
    u = actor(req)
    if not u:
        return None
    if u.get("app_role") != "HR":
        raise HTTPException(403, "HR access required")
    return u


@app.get("/hr/employees", response_class=HTMLResponse)
def hr_employees(req: Request, q: str = ""):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        rows = c.execute(
            "SELECT e.employee_id,e.full_name,e.work_email,e.employment_status,e.start_date,r.title role_title,d.name department_name "
            "FROM employees e JOIN roles r ON r.role_id=e.role_id JOIN departments d ON d.department_id=e.department_id "
            "WHERE e.employee_id LIKE ? OR e.full_name LIKE ? OR e.work_email LIKE ? ORDER BY e.employee_id LIMIT 100",
            (like, like, like),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT e.employee_id,e.full_name,e.work_email,e.employment_status,e.start_date,r.title role_title,d.name department_name "
            "FROM employees e JOIN roles r ON r.role_id=e.role_id JOIN departments d ON d.department_id=e.department_id "
            "ORDER BY e.employee_id LIMIT 100"
        ).fetchall()
    c.close()
    items = "".join(
        f'<tr><td><a href="/hr/employees/{escape(x["employee_id"])}">{escape(x["employee_id"])}</a></td>'
        f'<td>{escape(x["full_name"])}</td><td>{escape(x["work_email"])}</td><td>{escape(x["role_title"])}</td>'
        f'<td>{escape(x["department_name"])}</td><td>{escape(x["employment_status"])}</td><td>{escape(x["start_date"])}</td></tr>'
        for x in rows
    ) or '<tr><td colspan="7">No employees found.</td></tr>'
    body = (
        '<p><a class="action-link" href="/hr/employees/new">+ Create employee</a></p>'
        f'<form method="get"><label>Search employees<input name="q" value="{escape(term)}" placeholder="Name, employee ID or email"></label><button>Search</button></form>'
        '<div class="table-wrap"><table><thead><tr><th>Employee ID</th><th>Name</th><th>Email</th><th>Role</th><th>Department</th><th>Status</th><th>Start date</th></tr></thead>'
        f'<tbody>{items}</tbody></table></div>'
        '<p>Showing up to 100 matching employee records.</p>'
    )
    return render("HR · Employee directory", body, u)


@app.get("/hr/employees/new", response_class=HTMLResponse)
def hr_employee_new_page(req: Request):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    roles = c.execute("SELECT role_id,title,department_id FROM roles WHERE active_flag=1 ORDER BY title").fetchall()
    managers = c.execute("SELECT employee_id,full_name FROM employees WHERE employment_status='ACTIVE' ORDER BY full_name LIMIT 500").fetchall()
    c.close()
    role_options = "".join(f'<option value="{escape(x["role_id"])}">{escape(x["title"])} · {escape(x["department_id"])}</option>' for x in roles)
    manager_options = '<option value="">No manager assigned</option>' + "".join(f'<option value="{escape(x["employee_id"])}">{escape(x["full_name"])} · {escape(x["employee_id"])}</option>' for x in managers)
    body = (
        '<p><a href="/hr/employees">← Back to employee directory</a></p>'
        '<form method="post" action="/hr/employees">'
        '<label>Full name<input name="full_name" maxlength="160" required></label>'
        '<label>Company email<input name="work_email" type="email" required></label>'
        '<label>Worker type<select name="worker_type"><option>EMPLOYEE</option><option>CONTRACTOR</option><option>INTERN</option><option>TEMPORARY</option></select></label>'
        f'<label>Job role<select name="role_id" required>{role_options}</select></label>'
        f'<label>Manager<select name="manager_id">{manager_options}</select></label>'
        '<label>Hire date<input name="hire_date" type="date" required></label>'
        '<label>Planned start date<input name="start_date" type="date" required></label>'
        '<label>Contract end date (required for contractors)<input name="contract_end_date" type="date"></label>'
        '<label>Work location<input name="location" placeholder="e.g. Hyderabad" required></label>'
        '<label>HR notes<input name="hr_notes" maxlength="1000"></label>'
        '<button type="submit">Create employee & onboarding case</button></form>'
    )
    return render("HR · Create employee", body, u)


@app.post("/hr/employees", response_class=HTMLResponse)
def hr_employee_create(
    req: Request, full_name: str = Form(...), work_email: str = Form(...), worker_type: str = Form("EMPLOYEE"),
    role_id: str = Form(...), manager_id: str = Form(""), hire_date: str = Form(...), start_date: str = Form(...),
    contract_end_date: str = Form(""), location: str = Form(...), hr_notes: str = Form(""),
):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    data = {
        "full_name": full_name, "work_email": work_email, "worker_type": worker_type,
        "role_id": role_id, "manager_id": manager_id, "hire_date": hire_date,
        "start_date": start_date, "contract_end_date": contract_end_date,
        "location": location, "hr_notes": hr_notes,
    }
    try:
        result = hr_service.create_employee(c, data, u)
    except ValueError as exc:
        c.close()
        return HTMLResponse(render("HR · Create employee", f'<p class="error">{escape(str(exc))}</p><a href="/hr/employees/new">Return to form</a>', u), status_code=400)
    c.close()
    return RedirectResponse(f'/hr/employees/{result["employee_id"]}?created=1', 303)


@app.get("/hr/employees/{employee_id}", response_class=HTMLResponse)
def hr_employee_detail(req: Request, employee_id: str, created: int = 0):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    employee = c.execute(
        "SELECT e.*,r.title role_title,d.name department_name FROM employees e JOIN roles r ON r.role_id=e.role_id JOIN departments d ON d.department_id=e.department_id WHERE e.employee_id=?",
        (employee_id,),
    ).fetchone()
    if not employee:
        c.close()
        raise HTTPException(404, "Employee not found")
    cases = c.execute("SELECT * FROM onboarding_cases WHERE employee_id=? ORDER BY opened_date DESC", (employee_id,)).fetchall()
    offboarding = c.execute("SELECT * FROM offboarding_cases WHERE employee_id=? ORDER BY notice_date DESC", (employee_id,)).fetchall()
    roles = c.execute("SELECT role_id,title FROM roles WHERE active_flag=1 ORDER BY title").fetchall()
    c.close()
    e = dict(employee)
    notice = '<p class="success">Employee and onboarding case created successfully.</p>' if created else ''
    case_rows = "".join(f'<li>{escape(x["case_id"])} · {escape(x["status"])} · planned start {escape(x["planned_start_date"])}</li>' for x in cases) or '<li>No onboarding case</li>'
    off_rows = "".join(f'<li>{escape(x["offboarding_id"])} · {escape(x["status"])} · last day {escape(x["last_working_day"])}</li>' for x in offboarding) or '<li>No offboarding case</li>'
    role_options = "".join(f'<option value="{escape(x["role_id"])}" {"selected" if x["role_id"]==e["role_id"] else ""}>{escape(x["title"])}</option>' for x in roles)
    body = (
        f'{notice}<p><a href="/hr/employees">← Employee directory</a></p>'
        f'<article><h2>{escape(e["full_name"])}</h2><p>{escape(e["employee_id"])} · {escape(e["work_email"])}</p>'
        f'<p><b>Status:</b> {escape(e["employment_status"])} &nbsp; <b>Worker type:</b> {escape(e["worker_type"])}</p>'
        f'<p><b>Role:</b> {escape(e["role_title"])} · <b>Department:</b> {escape(e["department_name"])}</p>'
        f'<p><b>Hire date:</b> {escape(e["hire_date"])} · <b>Start date:</b> {escape(e["start_date"])}</p></article>'
        f'<section><h2>Onboarding cases</h2><ul>{case_rows}</ul><h2>Offboarding cases</h2><ul>{off_rows}</ul></section>'
    )
    if e["employment_status"] != "TERMINATED":
        body += (
            '<section><h2>Change job role</h2><form method="post" action="/hr/employees/' + escape(employee_id) + '/role">'
            f'<label>New role<select name="role_id">{role_options}</select></label>'
            '<label>Effective date<input name="effective_date" type="date" required></label>'
            '<label>Reason<input name="reason" required maxlength="500"></label><button>Apply role change</button></form></section>'
            '<section><h2>Change start date</h2><form method="post" action="/hr/employees/' + escape(employee_id) + '/start-date">'
            '<label>New start date<input name="new_start_date" type="date" required></label>'
            '<label>Reason<input name="reason" required maxlength="500"></label><button>Update start date</button></form></section>'
            '<section><h2>Initiate termination / offboarding</h2><form method="post" action="/hr/employees/' + escape(employee_id) + '/terminate">'
            '<label>Last working day<input name="last_working_day" type="date" required></label>'
            '<label>Termination type<select name="termination_type"><option>VOLUNTARY</option><option>INVOLUNTARY</option><option>CONTRACT_END</option><option>URGENT</option></select></label>'
            '<label>HR reason<input name="reason" required maxlength="1000"></label><button>Start offboarding</button></form></section>'
        )
    return render("HR · Employee record", body, u)


@app.post("/hr/employees/{employee_id}/role")
def hr_employee_role_change(req: Request, employee_id: str, role_id: str = Form(...), effective_date: str = Form(...), reason: str = Form(...)):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        hr_service.change_employee_role(c, employee_id, role_id, effective_date, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(f"/hr/employees/{employee_id}", 303)


@app.post("/hr/employees/{employee_id}/start-date")
def hr_employee_start_date_change(req: Request, employee_id: str, new_start_date: str = Form(...), reason: str = Form(...)):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        hr_service.change_start_date(c, employee_id, new_start_date, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(f"/hr/employees/{employee_id}", 303)


@app.post("/hr/employees/{employee_id}/terminate")
def hr_employee_terminate(req: Request, employee_id: str, last_working_day: str = Form(...), termination_type: str = Form(...), reason: str = Form(...)):
    u = _hr_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        hr_service.terminate_employee(c, employee_id, last_working_day, termination_type, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(f"/hr/employees/{employee_id}", 303)


# Build 04: Manager team workspace, access decisions and readiness monitoring
def _manager_actor(req):
    u = actor(req)
    if not u:
        return None
    if u.get("app_role") != "MANAGER":
        raise HTTPException(403, "Manager access required")
    if not u.get("employee_id"):
        raise HTTPException(403, "Manager account is not linked to an employee record")
    return u


@app.get("/manager/team", response_class=HTMLResponse)
def manager_team(req: Request):
    u = _manager_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = manager_service.team_overview(c, u["employee_id"])
    c.close()
    items = "".join(
        f'<tr><td>{escape(x["employee_id"])}</td><td>{escape(x["full_name"])}</td>'
        f'<td>{escape(x["role_title"] or "")}</td><td>{escape(x["department_name"] or "")}</td>'
        f'<td>{escape(x["employment_status"])}</td><td>{escape(x["start_date"])}</td>'
        f'<td>{x["done_tasks"] or 0}/{x["total_tasks"] or 0} ({x["readiness_percent"]}%)</td></tr>'
        for x in rows
    ) or '<tr><td colspan="7">No direct reports are assigned to this manager.</td></tr>'
    body = ('<p><a href="/portal/manager">← Manager dashboard</a></p>'
            '<div class="table-wrap"><table><thead><tr><th>Employee ID</th><th>Name</th><th>Role</th><th>Department</th><th>Status</th><th>Start date</th><th>Onboarding readiness</th></tr></thead>'
            f'<tbody>{items}</tbody></table></div>')
    return render("Manager · My team", body, u)


@app.get("/manager/access-requests", response_class=HTMLResponse)
def manager_access_requests(req: Request):
    u = _manager_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = manager_service.pending_access_requests(c, u["employee_id"])
    c.close()
    cards = []
    for x in rows:
        cards.append(
            '<section><h2>' + escape(x["system_name"]) + ' · ' + escape(x["privilege_level"]) + '</h2>'
            + '<p><b>Request:</b> ' + escape(x["request_id"]) + ' · <b>Employee:</b> '
            + escape(x["full_name"]) + ' (' + escape(x["employee_id"]) + ')</p>'
            + '<p><b>Business justification:</b> ' + escape(x["business_justification"]) + '</p>'
            + '<form method="post" action="/manager/access-requests/' + escape(x["request_id"]) + '/decision">'
            + '<label>Decision<select name="decision"><option value="APPROVE">Approve – send to IT</option><option value="REJECT">Reject</option><option value="REVERIFY">Request re-verification</option></select></label>'
            + '<label>Reason<textarea name="reason" maxlength="1000" required></textarea></label>'
            + '<button type="submit">Submit decision</button></form></section>'
        )
    body = '<p><a href="/portal/manager">← Manager dashboard</a></p>' + (''.join(cards) or '<p>No access requests are currently awaiting your review.</p>')
    return render("Manager · Access approvals", body, u)


@app.post("/manager/access-requests/{request_id}/decision")
def manager_access_decision(req: Request, request_id: str, decision: str = Form(...), reason: str = Form(...)):
    u = _manager_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        manager_service.decide_access_request(c, request_id, decision, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/manager/access-requests", 303)


@app.get("/manager/tasks", response_class=HTMLResponse)
def manager_tasks(req: Request, status: str = ""):
    u = _manager_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    allowed_statuses = {"", "PENDING", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED"}
    if status not in allowed_statuses:
        raise HTTPException(400, "Invalid task status filter")
    c = connect()
    rows = manager_service.team_tasks(c, u["employee_id"], status or None)
    c.close()
    items = "".join(
        f'<tr><td>{escape(x["task_id"])}</td><td>{escape(x["full_name"])}</td><td>{escape(x["title"])}</td>'
        f'<td>{escape(x["owner_team"])}</td><td>{escape(x["status"])}</td><td>{escape(x["due_date"])}</td><td>{escape(x["priority"])}</td></tr>'
        for x in rows
    ) or '<tr><td colspan="7">No onboarding tasks found for your team.</td></tr>'
    options = ''.join(f'<option value="{x}" {"selected" if status==x else ""}>{x or "ALL"}</option>' for x in sorted(allowed_statuses))
    body = ('<p><a href="/portal/manager">← Manager dashboard</a></p>'
            f'<form method="get"><label>Task status<select name="status">{options}</select></label><button>Filter</button></form>'
            '<div class="table-wrap"><table><thead><tr><th>Task ID</th><th>Employee</th><th>Task</th><th>Owner team</th><th>Status</th><th>Due date</th><th>Priority</th></tr></thead>'
            f'<tbody>{items}</tbody></table></div><p>Showing up to 500 tasks belonging to your direct reports.</p>')
    return render("Manager · Onboarding tasks", body, u)


# Build 05: IT & Operations workspace
def _it_actor(req):
    u = actor(req)
    if not u:
        return None
    if u.get("app_role") != "IT":
        raise HTTPException(403, "IT / Operations access required")
    return u


@app.get("/it/access-requests", response_class=HTMLResponse)
def it_access_requests(req: Request):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = it_service.pending_provisioning(c)
    c.close()
    cards = []
    for x in rows:
        cards.append(
            f'<article><h3>{escape(x["full_name"])} · {escape(x["employee_id"])}</h3>'
            f'<p>{escape(x["system_name"])} · {escape(x["privilege_level"])} · Start: {escape(x["start_date"])}</p>'
            f'<p>{escape(x["business_justification"])}</p>'
            f'<form method="post" action="/it/access-requests/{escape(x["request_id"])}/provision">'
            '<button>Provision access</button></form>'
            f'<form method="post" action="/it/access-requests/{escape(x["request_id"])}/reject">'
            '<label>Rejection reason<input name="reason" required maxlength="500"></label>'
            '<button class="danger">Reject with reason</button></form></article>'
        )
    body = '<p><a href="/portal/it">← IT dashboard</a></p>' + ("".join(cards) or "<p>No manager-approved requests are awaiting IT provisioning.</p>")
    return render("IT · Access provisioning queue", body, u)


@app.post("/it/access-requests/{request_id}/provision")
def it_provision_access(req: Request, request_id: str):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.provision_access(c, request_id, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/access-requests", 303)


@app.post("/it/access-requests/{request_id}/reject")
def it_reject_access(req: Request, request_id: str, reason: str = Form(...)):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.reject_access(c, request_id, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/access-requests", 303)


@app.get("/it/grants", response_class=HTMLResponse)
def it_grants(req: Request):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = it_service.list_grants(c)
    c.close()
    items = []
    for x in rows:
        action = ""
        if x["status"] == "GRANTED":
            action = (
                f'<form method="post" action="/it/grants/{escape(x["grant_id"])}/revoke">'
                '<label>Revocation reason<input name="reason" required maxlength="500"></label>'
                '<button class="danger">Revoke access</button></form>'
            )
        items.append(
            f'<tr><td>{escape(x["grant_id"])}</td><td>{escape(x["full_name"])}</td>'
            f'<td>{escape(x["system_name"])}</td><td>{escape(x["privilege_level"])}</td>'
            f'<td>{escape(x["status"])}</td><td>{action}</td></tr>'
        )
    body = '<p><a href="/portal/it">← IT dashboard</a></p><div class="table-wrap"><table><thead><tr><th>Grant</th><th>Employee</th><th>System</th><th>Privilege</th><th>Status</th><th>Action</th></tr></thead><tbody>' + ("".join(items) or '<tr><td colspan="6">No grants found.</td></tr>') + '</tbody></table></div>'
    return render("IT · Access grants", body, u)


@app.post("/it/grants/{grant_id}/revoke")
def it_revoke_access(req: Request, grant_id: str, reason: str = Form(...)):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.revoke_access(c, grant_id, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/grants", 303)


@app.get("/it/assets", response_class=HTMLResponse)
def it_assets(req: Request):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    assets = it_service.asset_inventory(c)
    employees = c.execute(
        "SELECT employee_id,full_name FROM employees WHERE employment_status!='TERMINATED' ORDER BY full_name LIMIT 500"
    ).fetchall()
    assignments = c.execute(
        """SELECT aa.assignment_id,aa.status,aa.employee_id,e.full_name,a.asset_type,a.serial_number
           FROM asset_assignments aa JOIN employees e ON e.employee_id=aa.employee_id
           JOIN assets a ON a.asset_id=aa.asset_id
           WHERE aa.status IN ('ASSIGNED','DELIVERED') ORDER BY aa.assigned_date DESC LIMIT 300"""
    ).fetchall()
    mismatches = it_service.reconcile_assets(c)
    c.close()
    available = [x for x in assets if x["current_status"] == "IN_STOCK"]
    asset_options = "".join(
        f'<option value="{escape(x["asset_id"])}">{escape(x["asset_type"])} · {escape(x["serial_number"])} · {escape(x["model"])}</option>'
        for x in available
    )
    employee_options = "".join(
        f'<option value="{escape(x["employee_id"])}">{escape(x["full_name"])} · {escape(x["employee_id"])}</option>'
        for x in employees
    )
    assignment_rows = []
    for x in assignments:
        delivery = ""
        if x["status"] == "ASSIGNED":
            delivery = f'<form method="post" action="/it/assets/{escape(x["assignment_id"])}/deliver"><button>Mark delivered</button></form>'
        assignment_rows.append(
            f'<tr><td>{escape(x["assignment_id"])}</td><td>{escape(x["asset_type"])} · {escape(x["serial_number"])}</td>'
            f'<td>{escape(x["full_name"])}</td><td>{escape(x["status"])}</td><td>{delivery}'
            f'<form method="post" action="/it/assets/{escape(x["assignment_id"])}/recover">'
            '<label>Recovery reason<input name="reason" required maxlength="500"></label>'
            '<button class="danger">Record recovery</button></form></td></tr>'
        )
    body = (
        '<p><a href="/portal/it">← IT dashboard</a></p>'
        f'<section><h2>Available inventory</h2><p>{len(available)} assets currently in stock.</p>'
        '<form method="post" action="/it/assets/assign">'
        f'<label>Asset<select name="asset_id" required>{asset_options}</select></label>'
        f'<label>Employee<select name="employee_id" required>{employee_options}</select></label>'
        '<label>Assignment reason<input name="reason" required maxlength="500"></label>'
        '<button>Assign asset</button></form></section>'
        f'<section><h2>Active assignments</h2><p>Reconciliation discrepancies: {len(mismatches)}</p>'
        '<div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Asset</th><th>Employee</th><th>Status</th><th>Actions</th></tr></thead><tbody>'
        + ("".join(assignment_rows) or '<tr><td colspan="5">No active assignments.</td></tr>')
        + '</tbody></table></div></section>'
    )
    if mismatches:
        body += '<section><h2>Reconciliation exceptions</h2><ul>' + "".join(
            f'<li>{escape(x["assignment_id"])} · {escape(x["asset_id"])} · assignment {escape(x["status"])} / asset {escape(x["current_status"])}</li>'
            for x in mismatches
        ) + '</ul></section>'
    return render("IT · Asset operations", body, u)


@app.post("/it/assets/assign")
def it_assign_asset(req: Request, asset_id: str = Form(...), employee_id: str = Form(...), reason: str = Form(...)):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.assign_asset(c, asset_id, employee_id, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/assets", 303)


@app.post("/it/assets/{assignment_id}/deliver")
def it_deliver_asset(req: Request, assignment_id: str):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.mark_asset_delivered(c, assignment_id, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/assets", 303)


@app.post("/it/assets/{assignment_id}/recover")
def it_recover_asset(req: Request, assignment_id: str, reason: str = Form(...)):
    u = _it_actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        it_service.recover_asset(c, assignment_id, reason, u)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/it/assets", 303)


# Build 06: Employee self-service portal
def _employee_actor(req):
    u = actor(req)
    if not u:
        return None
    if u.get("app_role") != "EMPLOYEE":
        raise HTTPException(403, "Employee access required")
    if not u.get("employee_id"):
        raise HTTPException(403, "Employee account is not linked to an employee record")
    return u


@app.post("/employee/tasks/{task_id}/complete")
def employee_task_complete(req: Request, task_id: str):
    u = _employee_actor(req)
    if not u: return RedirectResponse("/login", 303)
    c = connect()
    try:
        employee_service.complete_employee_task(c, u["employee_id"], task_id, u)
    except ValueError as exc:
        c.close(); raise HTTPException(400, str(exc))
    c.close(); return RedirectResponse("/portal/employee", 303)


@app.post("/employee/access-requests")
def employee_access_request(req: Request, access_role_id: str = Form(...), business_justification: str = Form(...)):
    u = _employee_actor(req)
    if not u: return RedirectResponse("/login", 303)
    c = connect()
    try:
        employee_service.request_access(c, u["employee_id"], access_role_id, business_justification, u)
    except ValueError as exc:
        c.close()
        req.session['flash_message'] = str(exc)
        return RedirectResponse("/portal/employee", 303)
    c.close()
    req.session['flash_message'] = "Access request submitted successfully and sent to your manager for review."
    return RedirectResponse("/portal/employee", 303)


@app.post("/employee/assets/{assignment_id}/acknowledge")
def employee_asset_acknowledge(req: Request, assignment_id: str):
    u = _employee_actor(req)
    if not u: return RedirectResponse("/login", 303)
    c = connect()
    try:
        employee_service.acknowledge_asset(c, u["employee_id"], assignment_id, u)
    except ValueError as exc:
        c.close(); raise HTTPException(400, str(exc))
    c.close(); return RedirectResponse("/portal/employee", 303)


@app.post("/employee/notifications/read")
def employee_notifications_read(req: Request):
    u = _employee_actor(req)
    if not u: return RedirectResponse("/login", 303)
    c = connect(); employee_service.mark_notifications_read(c, u["user_id"]); c.close()
    return RedirectResponse("/portal/employee", 303)



# Build 09: employee document upload and HR verification
@app.post("/employee/documents")
def employee_document_upload(req: Request, document_type: str = Form(...), upload: UploadFile = File(...)):
    u = actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    if u.get("app_role") != "EMPLOYEE" or not u.get("employee_id"):
        raise HTTPException(403, "Employee document upload is restricted to employees")
    c = connect()
    try:
        document_service.upload_document(
            c, u["employee_id"], {**u, "document_type": document_type},
            upload.filename, upload.content_type, upload.file.read(5 * 1024 * 1024 + 1)
        )
        req.session["flash_message"] = "Document uploaded successfully and sent to HR for review."
    except ValueError as exc:
        req.session["flash_message"] = str(exc)
    finally:
        upload.file.close()
        c.close()
    return RedirectResponse("/portal/employee", 303)


@app.get("/hr/documents", response_class=HTMLResponse)
def hr_documents_queue(req: Request):
    u = actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    if u.get("app_role") != "HR":
        raise HTTPException(403, "HR access required")
    c = connect()
    rows = c.execute(
        """SELECT d.*,e.full_name FROM employee_documents d JOIN employees e ON e.employee_id=d.employee_id
           ORDER BY CASE d.status WHEN 'PENDING_REVIEW' THEN 0 ELSE 1 END,d.uploaded_at DESC"""
    ).fetchall()
    c.close()
    table = ''.join(
        f'<tr><td>{escape(d["document_id"])}</td><td>{escape(d["full_name"])} · {escape(d["employee_id"])}</td>'
        f'<td>{escape(d["document_type"])}</td><td>{escape(d["original_filename"])}</td><td>{d["file_size"]} bytes</td>'
        f'<td>{escape(d["status"])}</td><td><a href="/hr/documents/{escape(d["document_id"])}/download">Download</a></td>'
        f'<td>{(f"""<form method="post" action="/hr/documents/{escape(d["document_id"])}/review"><label>Review note<input name="note" required maxlength="500"></label><button name="decision" value="VERIFIED">Verify</button><button class="danger" name="decision" value="REJECTED">Reject</button></form>""") if d["status"]=="PENDING_REVIEW" else escape(d["review_note"] or "")}</td></tr>'
        for d in rows
    ) or '<tr><td colspan="8">No employee documents submitted.</td></tr>'
    body = ('<p><a href="/portal/hr">← HR dashboard</a></p><h2>Employee document review</h2>'
            '<p>Review submitted files and record a reason for every decision.</p>'
            '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Employee</th><th>Category</th><th>File</th><th>Size</th><th>Status</th><th>File</th><th>Review</th></tr></thead>'
            f'<tbody>{table}</tbody></table></div>')
    return render("HR · Document verification", body, u)


@app.get("/hr/documents/{document_id}/download")
def hr_document_download(req: Request, document_id: str):
    u = actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    if u.get("app_role") != "HR":
        raise HTTPException(403, "HR access required")
    c = connect()
    try:
        path = document_service.document_file_path(c, document_id)
        row = c.execute("SELECT original_filename,content_type FROM employee_documents WHERE document_id=?", (document_id,)).fetchone()
    except ValueError as exc:
        c.close()
        raise HTTPException(404, str(exc))
    c.close()
    return FileResponse(path, media_type=row["content_type"], filename=row["original_filename"])


@app.post("/hr/documents/{document_id}/review")
def hr_document_review(req: Request, document_id: str, decision: str = Form(...), note: str = Form(...)):
    u = actor(req)
    if not u:
        return RedirectResponse("/login", 303)
    if u.get("app_role") != "HR":
        raise HTTPException(403, "HR access required")
    c = connect()
    try:
        document_service.review_document(c, document_id, u, decision, note)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/hr/documents", 303)


# Build 07: Cross-role offboarding workspace
def _offboarding_role(req, allowed):
    u = actor(req)
    if not u:
        return None
    if u.get("app_role") not in allowed:
        raise HTTPException(403, "Offboarding access denied")
    return u


@app.get("/hr/offboarding", response_class=HTMLResponse)
def hr_offboarding_workspace(req: Request):
    u = _offboarding_role(req, {"HR"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = offboarding_service.list_cases(c)
    c.close()
    table = "".join(
        f'<tr><td><a href="/hr/offboarding/{escape(x["offboarding_id"])}">{escape(x["offboarding_id"])}</a></td>'
        f'<td>{escape(x["full_name"])}</td><td>{escape(x["termination_type"])}</td>'
        f'<td>{escape(x["last_working_day"])}</td><td>{escape(x["status"])}</td>'
        f'<td>{"URGENT" if x["is_urgent"] else "Standard"}</td></tr>' for x in rows
    ) or '<tr><td colspan="6">No offboarding cases.</td></tr>'
    body = ('<p><a href="/portal/hr">← HR dashboard</a></p><h2>Offboarding cases</h2>'
            '<div class="table-wrap"><table><thead><tr><th>Case</th><th>Employee</th><th>Type</th><th>Last day</th><th>Status</th><th>Priority</th></tr></thead>'
            f'<tbody>{table}</tbody></table></div>')
    return render("HR · Offboarding", body, u)


@app.get("/hr/offboarding/{offboarding_id}", response_class=HTMLResponse)
def hr_offboarding_detail(req: Request, offboarding_id: str):
    u = _offboarding_role(req, {"HR"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        case, tasks, grants, assets = offboarding_service.case_detail(c, offboarding_id)
    except ValueError as exc:
        c.close()
        raise HTTPException(404, str(exc))
    c.close()
    task_rows = "".join(f'<tr><td>{escape(t["title"])}</td><td>{escape(t["owner_team"])}</td><td>{escape(t["status"])}</td><td>{escape(t["due_date"])}</td></tr>' for t in tasks)
    grant_rows = "".join(f'<li>{escape(g["system_name"])} · {escape(g["privilege_level"])} · {escape(g["status"])}</li>' for g in grants) or "<li>No access grants.</li>"
    asset_rows = "".join(f'<li>{escape(a["asset_type"])} · {escape(a["serial_number"])} · {escape(a["status"])}</li>' for a in assets) or "<li>All assets recovered.</li>"
    body = (f'<p><a href="/hr/offboarding">← Offboarding cases</a></p><h2>{escape(case["full_name"])} · {escape(offboarding_id)}</h2>'
            f'<p>Last working day: {escape(case["last_working_day"])} · Status: <b>{escape(case["status"])}</b> · '
            f'{"URGENT EXIT" if case["is_urgent"] else "Standard exit"}</p>'
            '<section><h2>Exit tasks</h2><div class="table-wrap"><table><thead><tr><th>Task</th><th>Owner</th><th>Status</th><th>Due</th></tr></thead>'
            f'<tbody>{task_rows}</tbody></table></div></section>'
            f'<section><h2>Access grants</h2><ul>{grant_rows}</ul></section><section><h2>Assets awaiting recovery</h2><ul>{asset_rows}</ul></section>')
    if case["status"] != "CLOSED":
        body += ('<section><h2>Close offboarding case</h2><p>Closure is allowed only when all exit tasks are complete, access grants are revoked and assets are recovered.</p>'
                 f'<form method="post" action="/hr/offboarding/{escape(offboarding_id)}/close">'
                 '<label>Closure note<input name="reason" maxlength="500" required></label><button class="danger">Verify and close case</button></form></section>')
    return render("HR · Offboarding detail", body, u)


@app.post("/hr/offboarding/{offboarding_id}/close")
def hr_offboarding_close(req: Request, offboarding_id: str, reason: str = Form(...)):
    u = _offboarding_role(req, {"HR"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        offboarding_service.close_case(c, offboarding_id, u, reason)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(f"/hr/offboarding/{offboarding_id}", 303)


@app.get("/manager/offboarding", response_class=HTMLResponse)
def manager_offboarding_workspace(req: Request):
    u = _offboarding_role(req, {"MANAGER"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = c.execute(
        """SELECT DISTINCT o.offboarding_id,o.employee_id,o.last_working_day,o.status,o.is_urgent,
                  e.full_name,t.task_id,t.title,t.status task_status,t.due_date
           FROM offboarding_cases o JOIN employees e ON e.employee_id=o.employee_id
           JOIN tasks t ON t.case_id=o.offboarding_id AND t.case_type='OFFBOARDING' AND t.owner_team='MANAGER'
           WHERE e.manager_id=? ORDER BY o.is_urgent DESC,o.last_working_day""", (u["employee_id"],)
    ).fetchall()
    c.close()
    cards = "".join(
        f'<section><h3>{escape(x["full_name"])} · {escape(x["offboarding_id"])}</h3>'
        f'<p>Last working day: {escape(x["last_working_day"])} · {escape(x["task_status"])}</p>'
        f'<form method="post" action="/manager/offboarding/{escape(x["task_id"])}/complete">'
        '<label>Handover completion note<input name="reason" required maxlength="500"></label>'
        '<button>Complete handover</button></form></section>' for x in rows
    ) or "<p>No offboarding handovers assigned to your team.</p>"
    return render("Manager · Offboarding handovers", '<p><a href="/portal/manager">← Manager dashboard</a></p>'+cards, u)


@app.post("/manager/offboarding/{task_id}/complete")
def manager_offboarding_complete(req: Request, task_id: str, reason: str = Form(...)):
    u = _offboarding_role(req, {"MANAGER"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    # Enforce that the task belongs to an employee reporting to this manager.
    owns = c.execute(
        """SELECT 1 FROM tasks t JOIN offboarding_cases o ON o.offboarding_id=t.case_id
           JOIN employees e ON e.employee_id=o.employee_id
           WHERE t.task_id=? AND t.case_type='OFFBOARDING' AND t.owner_team='MANAGER' AND e.manager_id=?""",
        (task_id, u["employee_id"])
    ).fetchone()
    if not owns:
        c.close()
        raise HTTPException(404, "Handover task not found for your team")
    try:
        offboarding_service.complete_owned_task(c, task_id, "MANAGER", u, reason)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/manager/offboarding", 303)


@app.get("/it/offboarding", response_class=HTMLResponse)
def it_offboarding_workspace(req: Request):
    u = _offboarding_role(req, {"IT"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    rows = c.execute(
        """SELECT o.offboarding_id,o.employee_id,o.last_working_day,o.status,o.is_urgent,e.full_name
           FROM offboarding_cases o JOIN employees e ON e.employee_id=o.employee_id
           WHERE o.status!='CLOSED' ORDER BY o.is_urgent DESC,o.last_working_day"""
    ).fetchall()
    c.close()
    cards = "".join(
        f'<section><h3>{escape(x["full_name"])} · {escape(x["offboarding_id"])}</h3>'
        f'<p>Last working day: {escape(x["last_working_day"])} · {"URGENT" if x["is_urgent"] else "Standard"}</p>'
        f'<a class="action-link" href="/it/offboarding/{escape(x["offboarding_id"])}">Open IT exit checklist</a></section>'
        for x in rows
    ) or "<p>No open offboarding cases.</p>"
    return render("IT · Offboarding", '<p><a href="/portal/it">← IT dashboard</a></p>'+cards, u)


@app.get("/it/offboarding/{offboarding_id}", response_class=HTMLResponse)
def it_offboarding_detail(req: Request, offboarding_id: str):
    u = _offboarding_role(req, {"IT"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        case, tasks, grants, assets = offboarding_service.case_detail(c, offboarding_id)
    except ValueError as exc:
        c.close()
        raise HTTPException(404, str(exc))
    c.close()
    grant_rows = "".join(
        f'<tr><td>{escape(g["system_name"])}</td><td>{escape(g["privilege_level"])}</td><td>{escape(g["status"])}</td>'
        + (f'<td><form method="post" action="/it/grants/{escape(g["grant_id"])}/revoke"><label>Reason<input name="reason" required></label><button class="danger">Revoke access</button></form></td>' if g["status"]=="GRANTED" else '<td>Revoked</td>') + '</tr>'
        for g in grants
    ) or '<tr><td colspan="4">No grants.</td></tr>'
    asset_rows = "".join(
        f'<tr><td>{escape(a["asset_type"])} · {escape(a["serial_number"])}</td><td>{escape(a["status"])}</td>'
        + (f'<td><form method="post" action="/it/assets/{escape(a["assignment_id"])}/recover"><label>Recovery reason<input name="reason" required></label><button class="danger">Record recovery</button></form></td>' if a["status"] in ("ASSIGNED","DELIVERED","ACKNOWLEDGED") else '<td>Recovered</td>') + '</tr>'
        for a in assets
    ) or '<tr><td colspan="3">No assets awaiting recovery.</td></tr>'
    body = (f'<p><a href="/it/offboarding">← IT offboarding queue</a></p><h2>{escape(case["full_name"])} · {escape(offboarding_id)}</h2>'
            f'<p>Last working day: {escape(case["last_working_day"])} · Status: {escape(case["status"])}</p>'
            '<section><h2>Revoke system access</h2><div class="table-wrap"><table><thead><tr><th>System</th><th>Privilege</th><th>Status</th><th>Action</th></tr></thead>'
            f'<tbody>{grant_rows}</tbody></table></div></section>'
            '<section><h2>Recover company assets</h2><div class="table-wrap"><table><thead><tr><th>Asset</th><th>Status</th><th>Action</th></tr></thead>'
            f'<tbody>{asset_rows}</tbody></table></div></section>')
    # IT-owned exit tasks can be explicitly completed after revocation/recovery.
    it_tasks = [t for t in tasks if t["owner_team"] == "IT" and t["status"] not in ("DONE","CANCELLED")]
    if it_tasks:
        body += '<section><h2>IT exit tasks</h2>'
        for t in it_tasks:
            body += (f'<form method="post" action="/it/offboarding/tasks/{escape(t["task_id"])}/complete">'
                     f'<p>{escape(t["title"])} · {escape(t["status"])}</p>'
                     '<label>Completion note<input name="reason" required maxlength="500"></label><button>Complete IT task</button></form>')
        body += '</section>'
    return render("IT · Offboarding detail", body, u)


@app.post("/it/offboarding/tasks/{task_id}/complete")
def it_offboarding_task_complete(req: Request, task_id: str, reason: str = Form(...)):
    u = _offboarding_role(req, {"IT"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        offboarding_service.complete_owned_task(c, task_id, "IT", u, reason)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(req.headers.get("referer", "/it/offboarding"), 303)


@app.post("/hr/offboarding/tasks/{task_id}/complete")
def hr_offboarding_task_complete(req: Request, task_id: str, reason: str = Form(...)):
    u = _offboarding_role(req, {"HR"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        offboarding_service.complete_owned_task(c, task_id, "HR", u, reason)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse("/hr/offboarding", 303)


@app.post("/it/offboarding/facilities/{task_id}/complete")
def it_facilities_task_complete(req: Request, task_id: str, reason: str = Form(...)):
    u = _offboarding_role(req, {"IT"})
    if not u:
        return RedirectResponse("/login", 303)
    c = connect()
    try:
        offboarding_service.complete_owned_task(c, task_id, "FACILITIES", u, reason)
    except ValueError as exc:
        c.close()
        raise HTTPException(400, str(exc))
    c.close()
    return RedirectResponse(req.headers.get("referer", "/it/offboarding"), 303)


# Build 10 foundation: System Administrator workspaces
def _admin_actor(req):
    u=actor(req)
    if not u: return None
    if u.get("app_role")!="SYSADMIN": raise HTTPException(403,"System Administrator access required")
    return u

def _admin_table(title, headers, rows, user, empty="No records found."):
    head="".join(f"<th>{escape(str(x))}</th>" for x in headers)
    body="".join("<tr>"+"".join(f"<td>{escape(str(v if v is not None else '—'))}</td>" for v in row)+"</tr>" for row in rows) or f'<tr><td colspan="{len(headers)}">{escape(empty)}</td></tr>'
    return render(title, f'<p><a href="/portal/admin">← Back to System Admin</a></p><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>', user)

@app.get("/admin/accounts",response_class=HTMLResponse)
def admin_accounts(req:Request):
    u=_admin_actor(req)
    if not u:return RedirectResponse("/login",303)
    c=connect(); rows=c.execute("SELECT user_id,email,app_role,account_status,failed_login_count,locked_until,last_login_at FROM user_accounts ORDER BY app_role,email").fetchall(); c.close()
    return _admin_table("User account administration",("User ID","Email","Role","Status","Failed logins","Locked until","Last login"),[tuple(x) for x in rows],u)

@app.get("/admin/audit",response_class=HTMLResponse)
def admin_audit(req:Request):
    u=_admin_actor(req)
    if not u:return RedirectResponse("/login",303)
    c=connect(); rows=c.execute("SELECT event_ts,actor_id,actor_role,action,entity_type,entity_id,reason FROM audit_events ORDER BY event_ts DESC LIMIT 250").fetchall(); c.close()
    return _admin_table("Audit trail",("Timestamp","Actor ID","Role","Action","Entity type","Entity ID","Reason"),[tuple(x) for x in rows],u,"No audit events have been recorded.")

@app.get("/admin/exceptions",response_class=HTMLResponse)
def admin_exceptions(req:Request):
    u=_admin_actor(req)
    if not u:return RedirectResponse("/login",303)
    c=connect(); rows=c.execute("SELECT exception_id,issue_type,entity_type,entity_id,severity,status,description,created_at FROM exception_records ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,created_at DESC LIMIT 300").fetchall(); c.close()
    return _admin_table("Workflow exceptions",("Exception ID","Issue","Entity type","Entity ID","Severity","Status","Description","Created"),[tuple(x) for x in rows],u,"No workflow exceptions recorded.")

@app.get("/admin/reconciliation",response_class=HTMLResponse)
def admin_reconciliation(req:Request):
    u=_admin_actor(req)
    if not u:return RedirectResponse("/login",303)
    c=connect(); rows=c.execute("SELECT reconciliation_id,entity_type,entity_id,status,details,checked_at FROM reconciliation_results ORDER BY checked_at DESC LIMIT 300").fetchall(); c.close()
    return _admin_table("Reconciliation results",("Run ID","Entity type","Entity ID","Status","Details","Checked at"),[tuple(x) for x in rows],u,"No reconciliation results recorded.")
