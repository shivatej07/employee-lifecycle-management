import json,csv
from collections import Counter
from pathlib import Path
from onboarding_sim.database import connect
from onboarding_sim.config import EXPORTS,REPORTS,GROUND_TRUTH
from onboarding_sim.detection.core import detect

def metrics(path=EXPORTS/'dataset.db'):
    c=connect(path);out={}
    for t in ('employees','tasks','access_grants','assets','onboarding_cases','offboarding_cases'):
        out[t]=c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    out['task_status']={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM tasks GROUP BY status')}
    out['employee_status']={r['employment_status']:r['n'] for r in c.execute('SELECT employment_status,COUNT(*) n FROM employees GROUP BY employment_status')}
    c.close();REPORTS.mkdir(parents=True,exist_ok=True)
    (REPORTS/'metrics_report.json').write_text(json.dumps(out,indent=2));return out

def anomaly_evaluation(path=EXPORTS/'dataset.db'):
    labels=list(csv.DictReader((GROUND_TRUTH/'ground_truth.csv').open(encoding='utf-8')))
    findings=detect(path)
    truth={(x['issue_type'],x['entity_id']) for x in labels}
    predicted={(x['issue_type'],x['entity_id']) for x in findings}
    categories=sorted({x[0] for x in truth}|{x[0] for x in predicted})
    result={}
    for category in categories:
        t={x for x in truth if x[0]==category};p={x for x in predicted if x[0]==category}
        tp=len(t&p);fp=len(p-t);fn=len(t-p)
        precision=tp/(tp+fp) if tp+fp else 0
        recall=tp/(tp+fn) if tp+fn else 0
        f1=2*precision*recall/(precision+recall) if precision+recall else 0
        result[category]={'TP':tp,'FP':fp,'FN':fn,'precision':round(precision,4),'recall':round(recall,4),'F1':round(f1,4)}
    REPORTS.mkdir(parents=True,exist_ok=True)
    (REPORTS/'anomaly_report.json').write_text(json.dumps(result,indent=2))
    return result
