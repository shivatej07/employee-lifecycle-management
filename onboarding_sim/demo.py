import shutil
from pathlib import Path
from onboarding_sim.config import EXPORTS,DB
from onboarding_sim.database import initialize
from onboarding_sim.auth.security import hash_password

DEMO_PASSWORD='Demo@2026!'
DEMO_USERS=[
 ('employee.demo@example.invalid','EMPLOYEE','EMP-000006'),
 ('manager.demo@example.invalid','MANAGER','EMP-000002'),
 ('hr.demo@example.invalid','HR','EMP-000003'),
 ('it.demo@example.invalid','IT','EMP-000004'),
 ('admin.demo@example.invalid','SYSADMIN','EMP-000005'),
]
def init_demo_database(reset=False):
    source=EXPORTS/'dataset.db'
    if not source.exists(): raise FileNotFoundError('Generate dataset first: python -m onboarding_sim generate')
    if reset and DB.exists(): DB.unlink()
    if not DB.exists(): shutil.copy2(source,DB)
    c=initialize(DB)
    # Give the demo manager a deterministic direct-report set.
    for i in range(11, min(31,c.execute('SELECT COUNT(*) FROM employees').fetchone()[0]+1)):
        c.execute('UPDATE employees SET manager_id=? WHERE employee_id=?',(DEMO_USERS[1][2],f'EMP-{i:06d}'))
    for email,role,eid in DEMO_USERS:
        existing = c.execute('SELECT user_id FROM user_accounts WHERE email=?',(email,)).fetchone()
        if existing:
            c.execute('UPDATE user_accounts SET employee_id=?,app_role=?,account_status=\'ACTIVE\' WHERE user_id=?',(eid,role,existing['user_id']))
            continue
        uid=f"USR-{c.execute('SELECT COUNT(*) FROM user_accounts').fetchone()[0]+1:06d}"
        c.execute('INSERT INTO user_accounts(user_id,employee_id,email,password_hash,app_role,account_status,created_at,must_change_password) VALUES(?,?,?,?,?,?,?,0)',
          (uid,eid,email,hash_password(DEMO_PASSWORD),role,'ACTIVE','2026-10-22T08:00:00'))
    c.commit();c.close()
    return {'database':str(DB),'demo_password':DEMO_PASSWORD,'accounts':[x[0] for x in DEMO_USERS]}
