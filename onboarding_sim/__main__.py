import argparse,json,uvicorn
from onboarding_sim.generator.core import generate
from onboarding_sim.validation.core import validate
from onboarding_sim.engine.core import run_engine
from onboarding_sim.detection.core import detect
from onboarding_sim.reporting.core import metrics,anomaly_evaluation
from onboarding_sim.database import initialize
from onboarding_sim.config import EXPORTS,DB
from onboarding_sim.demo import init_demo_database
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
 g=s.add_parser('generate');g.add_argument('--seed',type=int,default=20261022);g.add_argument('--scale',choices=['starter','full'],default='starter');g.add_argument('--out',default=str(EXPORTS));g.add_argument('--employees',type=int);g.add_argument('--tasks',type=int);g.add_argument('--grants',type=int);g.add_argument('--assets',type=int)
 for x in ['validate','run-engine','detect','report','reproduce','init-app','reset-app','create-admin','serve']:s.add_parser(x)
 a=p.parse_args()
 if a.cmd=='generate':print(json.dumps(generate(a.seed,a.scale,a.out,a.employees,a.tasks,a.grants,a.assets),indent=2))
 elif a.cmd=='validate':print(json.dumps(validate(),indent=2))
 elif a.cmd=='run-engine':print(json.dumps(run_engine(),indent=2))
 elif a.cmd=='detect':print(json.dumps(detect(),indent=2))
 elif a.cmd=='report':print(json.dumps({'metrics':metrics(),'anomaly_evaluation':anomaly_evaluation()},indent=2))
 elif a.cmd in ('init-app','reset-app'):
  print(json.dumps(init_demo_database(reset=(a.cmd=='reset-app')),indent=2))
 elif a.cmd=='reproduce':
  x=generate(20261022,'starter',EXPORTS/'repro_a');y=generate(20261022,'starter',EXPORTS/'repro_b');print('same requested counts:',x['requested_counts']==y['requested_counts'])
 elif a.cmd=='create-admin':
  from onboarding_sim.demo import DEMO_PASSWORD
  print('For local demo only, SYSADMIN account admin.demo@example.invalid is seeded by init-app.')
  print('Change the demo password before any non-demo use.')
 elif a.cmd=='serve':uvicorn.run('onboarding_sim.web.main:app',host='127.0.0.1',port=8000)
if __name__=='__main__':main()
