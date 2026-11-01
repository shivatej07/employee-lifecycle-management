from onboarding_sim.database import connect,transaction
from onboarding_sim.config import DB
def run_engine(path=DB):
    c=connect(path); changed=0
    with transaction(c):
        for r in c.execute('SELECT task_id,status FROM tasks').fetchall():
            deps=c.execute('SELECT t.status FROM dependencies d JOIN tasks t ON t.task_id=d.depends_on_task_id WHERE d.task_id=?',(r['task_id'],)).fetchall()
            new='BLOCKED' if any(x['status']!='DONE' for x in deps) and r['status'] not in ('DONE','CANCELLED') else ('READY' if not deps and r['status'] in ('PENDING','BLOCKED') else r['status'])
            if new!=r['status']:c.execute('UPDATE tasks SET status=? WHERE task_id=?',(new,r['task_id']));changed+=1
    c.close();return {'tasks_recalculated':changed}
