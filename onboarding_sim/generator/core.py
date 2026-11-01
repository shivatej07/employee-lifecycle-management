import csv,random,json
from pathlib import Path
from datetime import date,timedelta
from onboarding_sim.ids import IdFactory
from onboarding_sim.database import initialize
from onboarding_sim.config import EXPORTS,GROUND_TRUTH,AS_OF,SEED
DEPTS=['Engineering','Finance','Human Resources','Operations','Sales','Marketing','Legal','Customer Success','Security','Data']
TITLES=['Software Engineer','Data Analyst','Product Manager','HR Partner','Finance Analyst','Operations Specialist','Security Engineer','Sales Executive','UX Designer','IT Support Engineer']
FIRST=['Aarav','Aditi','Vihaan','Anaya','Ishaan','Diya','Kabir','Meera','Arjun','Sara','Rohan','Tara']
LAST=['Sharma','Reddy','Patel','Rao','Khan','Iyer','Mehta','Nair','Das','Gupta']
TASKS=[('Identity verification','HR','VERIFICATION'),('Background check','HR','BACKGROUND'),('Contract signing','HR','CONTRACT'),('Create company account','IT','ACCOUNT'),('Access request review','MANAGER','APPROVAL'),('Provision approved access','IT','PROVISION'),('Prepare laptop','IT','EQUIPMENT'),('Deliver equipment','FACILITIES','DELIVERY'),('Acknowledge equipment','EMPLOYEE','ACK'),('Orientation','HR','ORIENTATION'),('Manager introduction','MANAGER','INTRO'),('Day-1 readiness','MANAGER','READINESS')]
def write_csv(path,rows):
    rows=list(rows)
    if not rows:return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def generate(seed=SEED,scale='starter',out=EXPORTS,employees=None,tasks=None,grants=None,assets=None):
    rng=random.Random(seed); ids=IdFactory(); out=Path(out);out.mkdir(parents=True,exist_ok=True); asof=date.fromisoformat(AS_OF)
    n=employees or (100 if scale=='starter' else 1000); nt=tasks or (800 if scale=='starter' else 8000); ng=grants or (150 if scale=='starter' else 1500); na=assets or (120 if scale=='starter' else 1200)
    depts=[{'department_id':ids.next('d','DEPT-',3),'name':x,'cost_center':f'CC-{i+100}','location_mode':['OFFICE','HYBRID','REMOTE'][i%3],'head_manager_id':None} for i,x in enumerate(DEPTS)]
    roles=[]
    for i in range(45):
        roles.append({'role_id':ids.next('r','ROLE-',3),'title':TITLES[i%10]+(f' {i//10+1}' if i>=10 else ''),'department_id':depts[i%10]['department_id'],'job_family':depts[i%10]['name'],'level':1+i%6,'default_worker_type':'EMPLOYEE','requires_equipment_profile':int(i%4!=0),'risk_tier':['LOW','MEDIUM','HIGH'][i%3],'active_flag':1})
    ars=[{'access_role_id':ids.next('a','ACR-',3),'system_name':['Email','ERP','CRM','Git','HRIS','VPN','Cloud Console','Analytics'][i%8],'privilege_level':['STANDARD','ELEVATED','ADMIN'][i%3],'requires_approval':int(i%3!=0),'approver_type':['MANAGER','IT','SECURITY'][i%3],'max_duration_days':365 if i%4 else 90} for i in range(32)]
    emps=[]
    for i in range(n):
        eid=ids.next('e','EMP-'); hire=asof-timedelta(days=rng.randint(10,280)); start=hire+timedelta(days=rng.randint(2,30))
        if i%10==0:start+=timedelta(days=7)
        term=(asof-timedelta(days=rng.randint(1,45))).isoformat() if i%9==0 else None
        emps.append({'employee_id':eid,'full_name':rng.choice(FIRST)+' '+rng.choice(LAST),'work_email':f'employee{i+1:04d}@example.invalid','worker_type':'CONTRACTOR' if i%8==0 else 'EMPLOYEE','role_id':roles[i%45]['role_id'],'department_id':depts[i%10]['department_id'],'manager_id':emps[rng.randrange(i)]['employee_id'] if i>10 and i%5==0 else None,'hire_date':hire.isoformat(),'start_date':start.isoformat(),'original_start_date':(start-timedelta(days=7) if i%10==0 else start).isoformat(),'contract_end_date':(asof+timedelta(days=90)).isoformat() if i%8==0 else None,'employment_status':'TERMINATED' if term else ('ACTIVE' if start<=asof else 'PRE_BOARDING'),'termination_date':term,'termination_type':'URGENT' if term and i%18==0 else ('VOLUNTARY' if term else None),'location':['Hyderabad','Bengaluru','Pune','Remote'][i%4],'hr_notes':f'Synthetic record {i+1}'})
    cases=[]; eligible=[e for e in emps if e['employment_status']!='TERMINATED'][:max(1,min(n,nt//8))]
    for e in eligible: cases.append({'case_id':ids.year('c','ONB-'),'employee_id':e['employee_id'],'case_type':'CONTRACTOR' if e['worker_type']=='CONTRACTOR' else 'NEW_HIRE','status':'IN_PROGRESS','opened_date':e['hire_date'],'planned_start_date':e['start_date'],'actual_start_date':e['start_date'] if e['employment_status']=='ACTIVE' else None,'completed_date':None})
    templates=[{'template_id':f'TPL-{i+1:03d}','title':x[0],'owner_team':x[1],'task_type':x[2],'optional_flag':int(i in (2,9)),'sla_hours':48 if i<8 else 72} for i,x in enumerate(TASKS)]
    taskrows=[]
    for i in range(nt):
        case=cases[i%len(cases)]; t=templates[i%len(templates)]; status=['DONE','READY','BLOCKED','IN_PROGRESS'][i%4]
        taskrows.append({'task_id':f"TASK-{case['case_id']}-{i//len(cases)+1:03d}",'case_id':case['case_id'],'case_type':'ONBOARDING','template_id':t['template_id'],'owner_team':t['owner_team'],'task_type':t['task_type'],'title':t['title'],'status':status,'due_date':(date.fromisoformat(case['planned_start_date'])-timedelta(days=3)).isoformat(),'completed_date':(asof-timedelta(days=2)).isoformat() if status=='DONE' else None,'sla_hours':t['sla_hours'],'priority':'URGENT' if i%37==0 else 'NORMAL'})
    grants=[]
    for i in range(ng):
        e=emps[i%n]; ar=ars[i%len(ars)]; st='REVOKED' if e['employment_status']=='TERMINATED' and i%2==0 else ('GRANTED' if e['employment_status']=='ACTIVE' else 'REQUESTED')
        grants.append({'grant_id':f"GRANT-{e['employee_id']}-{i//n+1:03d}",'employee_id':e['employee_id'],'access_role_id':ar['access_role_id'],'approval_id':None,'requested_date':e['hire_date'],'approved_date':e['hire_date'] if st=='GRANTED' else None,'granted_date':e['start_date'] if st=='GRANTED' else None,'effective_from':e['start_date'],'effective_to':None,'revoked_date':e['termination_date'] if st=='REVOKED' else None,'status':st,'granted_by':'SYSTEM' if st=='GRANTED' else None})
    anomaly_refs={k:[] for k in ['ACCESS_BEFORE_START_OR_APPROVAL','DUPLICATE_ASSET_ASSIGNMENT','TERMINATED_EMPLOYEE_RETAINS_GRANT','TASK_DEPENDENCY_CYCLE','RECOVERED_ASSET_REMAINS_ASSIGNED','OVERRIDE_WITHOUT_AUDIT']}
    # Inject access grants that were granted before the employee start date and without approval.
    eligible_people=[e for e in emps if e['employment_status']!='TERMINATED']
    for j,e in enumerate(eligible_people[:20]):
        g=next(x for x in grants if x['employee_id']==e['employee_id'])
        g['status']='GRANTED';g['approved_date']=None;g['granted_date']=(date.fromisoformat(e['start_date'])-timedelta(days=1)).isoformat();g['granted_by']='SYSTEM'
        anomaly_refs['ACCESS_BEFORE_START_OR_APPROVAL'].append(g['grant_id'])
    terminated_people=[e for e in emps if e['employment_status']=='TERMINATED']
    for j,e in enumerate(terminated_people[:20]):
        g=next((x for x in grants if x['employee_id']==e['employee_id']),None)
        if g:
            g['status']='GRANTED';g['revoked_date']=None;g['granted_date']=e['start_date'];g['granted_by']='SYSTEM'
            anomaly_refs['TERMINATED_EMPLOYEE_RETAINS_GRANT'].append(g['grant_id'])
    approvals=[]
    early_ids=set(anomaly_refs['ACCESS_BEFORE_START_OR_APPROVAL'])
    for g in grants:
        ar=next(x for x in ars if x['access_role_id']==g['access_role_id'])
        if g['status']=='GRANTED' and g['grant_id'] not in early_ids and ar['requires_approval']:
            aid=f"APR-{len(approvals)+1:06d}"
            approvals.append({'approval_id':aid,'employee_id':g['employee_id'],'request_type':'ACCESS','approver_id':'MANAGER-DEMO','decision':'APPROVED','reason':'Synthetic approved access request','decided_at':g['requested_date']+'T10:00:00'})
            g['approval_id']=aid;g['approved_date']=g['requested_date']
    assets=[{'asset_id':ids.next('asset','AST-'),'asset_type':['LAPTOP','MONITOR','PHONE','BADGE','DOCKING_STATION'][i%5],'serial_number':f'SYN-{seed}-{i+1:06d}','model':['ThinkPad T14','Dell Latitude 5450','MacBook Air','Dell P2425H','iPhone SE'][i%5],'purchase_date':(asof-timedelta(days=rng.randint(30,900))).isoformat(),'current_status':'ASSIGNED' if i%3 else 'IN_STOCK','current_holder_employee_id':emps[i%n]['employee_id'] if i%3 else None} for i in range(na)]
    assignments=[]
    for i,a in enumerate(assets):
        if a['current_status']=='ASSIGNED':
            assignments.append({'assignment_id':f'ASG-{len(assignments)+1:06d}','asset_id':a['asset_id'],'employee_id':a['current_holder_employee_id'],'assigned_date':a['purchase_date'],'delivery_date':a['purchase_date'],'acknowledged_date':None,'recovery_due_date':None,'recovered_date':None,'status':'DELIVERED'})
    # Duplicate assignment anomalies: create overlapping active history for selected assets.
    for j,a in enumerate([x for x in assets if x['current_status']=='ASSIGNED'][:20]):
        other=emps[(j+50)%n]
        assignments.append({'assignment_id':f'ASG-{len(assignments)+1:06d}','asset_id':a['asset_id'],'employee_id':other['employee_id'],'assigned_date':AS_OF,'delivery_date':None,'acknowledged_date':None,'recovery_due_date':None,'recovered_date':None,'status':'ASSIGNED'})
        anomaly_refs['DUPLICATE_ASSET_ASSIGNMENT'].append(a['asset_id'])
    # Recovered-but-still-assigned anomalies.
    for j,a in enumerate([x for x in assets if x['current_status']=='ASSIGNED'][20:40]):
        rec=next(x for x in assignments if x['asset_id']==a['asset_id'])
        rec['status']='RECOVERED';rec['recovered_date']=AS_OF
        anomaly_refs['RECOVERED_ASSET_REMAINS_ASSIGNED'].append(rec['assignment_id'])
    dependencies=[]
    by_case={}
    for t in taskrows: by_case.setdefault(t['case_id'],[]).append(t)
    for case_id,items in list(by_case.items())[:20]:
        if len(items)>=2:
            a,b=items[0],items[1]
            dependencies.append({'dependency_id':f'DEP-{len(dependencies)+1:06d}','task_id':a['task_id'],'depends_on_task_id':b['task_id'],'dependency_type':'FINISH_TO_START'})
            dependencies.append({'dependency_id':f'DEP-{len(dependencies)+1:06d}','task_id':b['task_id'],'depends_on_task_id':a['task_id'],'dependency_type':'FINISH_TO_START'})
            anomaly_refs['TASK_DEPENDENCY_CYCLE'].extend([a['task_id'],b['task_id']])
    # Seed one realistic pending access request for each manager with an eligible direct report.
    # These demo requests make the Manager Portal review queue usable before Employee self-service ships.
    access_requests=[]
    seen_managers=set()
    for i,e in enumerate(emps):
        manager_id=e['manager_id']
        if manager_id and manager_id not in seen_managers and e['employment_status']!='TERMINATED':
            seen_managers.add(manager_id)
            ar=ars[(i*7)%len(ars)]
            access_requests.append({'request_id':f'AR-{len(access_requests)+1:06d}','employee_id':e['employee_id'],
                'access_role_id':ar['access_role_id'],'business_justification':f'Synthetic business need for {ar["system_name"]} access',
                'status':'PENDING_MANAGER','manager_decision':None,'it_decision':None,'created_at':AS_OF+'T09:00:00'})
    workflow_decisions=[]
    for j in range(20):
        e=emps[(j*13)%n]
        workflow_decisions.append({'decision_id':f'DEC-{j+1:06d}','case_id':cases[j%len(cases)]['case_id'],'decision_type':'OVERRIDE','rule_id':'BR-008','inputs_ref':e['employee_id'],'outcome':'OVERRIDDEN','reason':'Synthetic unaudited override scenario','created_at':AS_OF+'T12:00:00'})
        anomaly_refs['OVERRIDE_WITHOUT_AUDIT'].append(e['employee_id'])
    off=[]
    for e in emps:
        if e['employment_status']=='TERMINATED':off.append({'offboarding_id':ids.year('off','OFF-'),'employee_id':e['employee_id'],'termination_type':e['termination_type'],'notice_date':e['termination_date'],'last_working_day':e['termination_date'],'status':'IN_PROGRESS','is_urgent':int(e['termination_type']=='URGENT'),'completed_date':None,'hr_reason':'Synthetic reason'})
    tables={'departments':depts,'roles':roles,'employees':emps,'onboarding_cases':cases,'task_templates':templates,'tasks':taskrows,'dependencies':dependencies,'access_roles':ars,'approvals':approvals,'access_grants':grants,'access_requests':access_requests,'assets':assets,'asset_assignments':assignments,'workflow_decisions':workflow_decisions,'offboarding_cases':off}
    for name,rows in tables.items():write_csv(out/f'{name}.csv',rows)
    db=out/'dataset.db'
    if db.exists():db.unlink()
    conn=initialize(db)
    for name,rows in tables.items():
        if rows:
            cols=list(rows[0]); marks=','.join('?' for _ in cols)
            for row in rows: conn.execute(f"INSERT INTO {name} ({','.join(cols)}) VALUES ({marks})",tuple(row[c] for c in cols))
    conn.commit();conn.close()
    GROUND_TRUTH.mkdir(parents=True,exist_ok=True)
    labels=[]
    types=list(anomaly_refs)
    for k,typ in enumerate(types):
        for j,entity_id in enumerate(anomaly_refs[typ]):
            entity_type='AccessGrant' if typ in ('ACCESS_BEFORE_START_OR_APPROVAL','TERMINATED_EMPLOYEE_RETAINS_GRANT') else ('Asset' if typ=='DUPLICATE_ASSET_ASSIGNMENT' else ('Task' if typ=='TASK_DEPENDENCY_CYCLE' else ('AssetAssignment' if typ=='RECOVERED_ASSET_REMAINS_ASSIGNED' else 'Employee')))
            labels.append({'anomaly_id':f'ANOM-{k+1:02d}-{j+1:03d}','issue_type':typ,'entity_type':entity_type,'entity_id':entity_id,'related_entity_ids':'','violated_rule_id':f'BR-{k+1:03d}','expected_decision':'ESCALATE','severity':'HIGH','injection_method':'deterministic operational record mutation','is_valid_exception':0})
    write_csv(GROUND_TRUTH/'ground_truth.csv',labels)
    manifest={'seed':seed,'as_of_date':AS_OF,'counts':{k:len(v) for k,v in tables.items()},'requested_counts':{'employees':n,'tasks':nt,'grants':ng,'assets':na},'synthetic_only':True}
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest
