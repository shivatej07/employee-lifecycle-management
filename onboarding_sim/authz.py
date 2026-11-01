ROLE_PERMISSIONS={
'EMPLOYEE':{'portal.employee','task.complete.own','asset.acknowledge.own','search.scoped'},
'MANAGER':{'portal.manager','approval.decide.team','task.complete.team','search.scoped'},
'HR':{'portal.hr','employee.manage','case.manage','termination.initiate','search.scoped'},
'IT':{'portal.it','grant.provision','grant.revoke','asset.manage','reconcile','search.scoped'},
'SYSADMIN':{'portal.admin','user.manage','audit.view.all','override.create','search.global','engine.run','detector.run'}}
PORTAL_PATHS={'EMPLOYEE':'/portal/employee','MANAGER':'/portal/manager','HR':'/portal/hr','IT':'/portal/it','SYSADMIN':'/portal/admin'}
def allowed(role,permission): return permission in ROLE_PERMISSIONS.get(role,set())
