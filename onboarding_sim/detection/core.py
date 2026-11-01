from onboarding_sim.database import connect
from onboarding_sim.config import DB

def detect(path=DB):
    # Detector reads operational tables only. It never imports or opens ground_truth.
    c=connect(path); out=[]
    rows=c.execute("""SELECT g.grant_id,g.employee_id FROM access_grants g
      JOIN employees e USING(employee_id) JOIN access_roles ar USING(access_role_id)
      WHERE g.status='GRANTED' AND (
        g.granted_date < e.start_date OR
        (ar.requires_approval=1 AND g.approval_id IS NULL)
      )""").fetchall()
    out += [{'issue_type':'ACCESS_BEFORE_START_OR_APPROVAL','entity_id':r['grant_id'],'employee_id':r['employee_id']} for r in rows]
    rows=c.execute("""SELECT a.asset_id,COUNT(*) n FROM asset_assignments x
      JOIN assets a USING(asset_id) WHERE x.status IN ('ASSIGNED','DELIVERED','ACKNOWLEDGED','RECOVERY_PENDING')
      GROUP BY a.asset_id HAVING n>1""").fetchall()
    out += [{'issue_type':'DUPLICATE_ASSET_ASSIGNMENT','entity_id':r['asset_id']} for r in rows]
    rows=c.execute("""SELECT g.grant_id,g.employee_id FROM access_grants g JOIN employees e USING(employee_id)
      WHERE e.employment_status='TERMINATED' AND g.status='GRANTED'""").fetchall()
    out += [{'issue_type':'TERMINATED_EMPLOYEE_RETAINS_GRANT','entity_id':r['grant_id'],'employee_id':r['employee_id']} for r in rows]
    deps=c.execute('SELECT task_id,depends_on_task_id FROM dependencies').fetchall()
    graph={}
    for r in deps: graph.setdefault(r['task_id'],set()).add(r['depends_on_task_id'])
    visiting=set();visited=set();cycles=set()
    def visit(node,path_nodes):
        if node in visiting:
            cycles.update(path_nodes[path_nodes.index(node):]);return
        if node in visited:return
        visiting.add(node);path_nodes.append(node)
        for nxt in graph.get(node,()):visit(nxt,path_nodes)
        path_nodes.pop();visiting.remove(node);visited.add(node)
    for node in graph:visit(node,[])
    out += [{'issue_type':'TASK_DEPENDENCY_CYCLE','entity_id':task_id} for task_id in sorted(cycles)]
    rows=c.execute("""SELECT x.assignment_id,x.asset_id FROM asset_assignments x JOIN assets a USING(asset_id)
      WHERE x.status='RECOVERED' AND a.current_status='ASSIGNED'""").fetchall()
    out += [{'issue_type':'RECOVERED_ASSET_REMAINS_ASSIGNED','entity_id':r['assignment_id'],'asset_id':r['asset_id']} for r in rows]
    rows=c.execute("""SELECT w.decision_id,w.inputs_ref FROM workflow_decisions w
      WHERE w.decision_type='OVERRIDE' AND NOT EXISTS (
        SELECT 1 FROM audit_events a WHERE a.entity_type='Employee' AND a.entity_id=w.inputs_ref AND a.action='OVERRIDE'
      )""").fetchall()
    out += [{'issue_type':'OVERRIDE_WITHOUT_AUDIT','entity_id':r['inputs_ref'],'decision_id':r['decision_id']} for r in rows]
    c.close();return out
