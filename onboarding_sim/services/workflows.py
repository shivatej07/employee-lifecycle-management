from onboarding_sim.database import transaction

def append_audit(conn,event_id,actor_id,actor_role,action,entity_type,entity_id,old_state,new_state,reason,ts='2026-10-22T12:00:00'):
    conn.execute('INSERT INTO audit_events(event_id,event_ts,actor_id,actor_role,action,entity_type,entity_id,from_state,to_state,reason,override_flag) VALUES(?,?,?,?,?,?,?,?,?,?,0)',
      (event_id,ts,actor_id,actor_role,action,entity_type,entity_id,old_state,new_state,reason))

def complete_task(conn,task_id,actor_id,actor_role,event_id):
    row=conn.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
    if row is None: raise ValueError('Task not found')
    if row['status'] not in ('READY','IN_PROGRESS'): raise ValueError('Task is not ready for completion')
    pending=conn.execute("SELECT COUNT(*) FROM dependencies d JOIN tasks t ON t.task_id=d.depends_on_task_id WHERE d.task_id=? AND t.status!='DONE'",(task_id,)).fetchone()[0]
    if pending: raise ValueError('Blocked by incomplete prerequisites (BR-001)')
    with transaction(conn):
        conn.execute("UPDATE tasks SET status='DONE',completed_date='2026-10-22' WHERE task_id=?",(task_id,))
        append_audit(conn,event_id,actor_id,actor_role,'STATE_CHANGE','Task',task_id,row['status'],'DONE','Task completed')
    return dict(conn.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone())
