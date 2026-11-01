def search(conn,actor,query,limit=30):
    query = (query or '').strip()
    if not query:
        return []
    q=f'%{query}%'; role=actor['app_role']
    if role in ('SYSADMIN','HR','IT'): rows=conn.execute('SELECT employee_id id,full_name label FROM employees WHERE employee_id LIKE ? OR full_name LIKE ? OR work_email LIKE ? ORDER BY employee_id LIMIT ?',(q,q,q,limit)).fetchall()
    elif role=='MANAGER': rows=conn.execute('SELECT employee_id id,full_name label FROM employees WHERE manager_id=? AND (employee_id LIKE ? OR full_name LIKE ? OR work_email LIKE ?) LIMIT ?',(actor['employee_id'],q,q,q,limit)).fetchall()
    else: rows=conn.execute('SELECT employee_id id,full_name label FROM employees WHERE employee_id=? AND (employee_id LIKE ? OR full_name LIKE ? OR work_email LIKE ?) LIMIT ?',(actor['employee_id'],q,q,q,limit)).fetchall()
    return [dict(x) for x in rows]
