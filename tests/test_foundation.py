from onboarding_sim.ids import IdFactory
from onboarding_sim.derive import delay_days,task_completion_percent
from onboarding_sim.auth.security import validate_password
def test_ids():assert IdFactory().next('e','EMP-')=='EMP-000001'
def test_delay():assert delay_days('2026-10-01','2026-10-08')==7
def test_completion():assert task_completion_percent([{'status':'DONE'},{'status':'READY'}])==50
def test_password():assert validate_password('GoodPass123!','u@example.invalid')
