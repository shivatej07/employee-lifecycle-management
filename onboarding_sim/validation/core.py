from onboarding_sim.database import connect
from onboarding_sim.config import EXPORTS
def validate(path=EXPORTS/'dataset.db'):
    c=connect(path); result={'foreign_key_violations':len(c.execute('PRAGMA foreign_key_check').fetchall())}
    for t in ('employees','tasks','access_grants','assets'): result[t]=c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    result['duplicate_serials']=c.execute('SELECT COUNT(*) FROM (SELECT serial_number FROM assets GROUP BY serial_number HAVING COUNT(*)>1)').fetchone()[0]
    c.close();result['passed']=result['foreign_key_violations']==0 and result['duplicate_serials']==0
    return result
