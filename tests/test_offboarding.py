from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import offboarding


def _db(tmp_path):
    out = tmp_path / "exports"
    generate(seed=20261022, scale="starter", out=out)
    return connect(out / "dataset.db")


def test_offboarding_case_cannot_close_until_tasks_grants_and_assets_clear(tmp_path):
    c = _db(tmp_path)
    employee = c.execute("SELECT employee_id FROM employees LIMIT 1").fetchone()[0]
    c.execute(
        """INSERT INTO offboarding_cases(offboarding_id,employee_id,termination_type,notice_date,last_working_day,status,is_urgent,hr_reason)
           VALUES('OFF-TEST-0001',?,?,? ,?,'IN_PROGRESS',0,'test')""",
        (employee, "VOLUNTARY", "2026-10-22", "2026-10-30")
    )
    c.execute(
        """INSERT INTO tasks(task_id,case_id,case_type,owner_team,task_type,title,status,due_date,sla_hours,priority)
           VALUES('TASK-OFF-TEST-001','OFF-TEST-0001','OFFBOARDING','MANAGER','HANDOVER','Team handover','READY','2026-10-30',48,'HIGH')"""
    )
    c.commit()
    actor = {"user_id": "USR-HR-TEST", "app_role": "HR"}
    try:
        offboarding.close_case(c, "OFF-TEST-0001", actor, "Close test")
        assert False, "Expected closure to be blocked by open task"
    except ValueError as exc:
        assert "task" in str(exc).lower()
    c.close()


def test_offboarding_task_completion_is_audited_and_case_can_close(tmp_path):
    c = _db(tmp_path)
    employee = c.execute("SELECT employee_id FROM employees LIMIT 1").fetchone()[0]
    c.execute(
        """INSERT INTO offboarding_cases(offboarding_id,employee_id,termination_type,notice_date,last_working_day,status,is_urgent,hr_reason)
           VALUES('OFF-TEST-0002',?,?,? ,?,'IN_PROGRESS',0,'test')""",
        (employee, "VOLUNTARY", "2026-10-22", "2026-10-30")
    )
    c.execute(
        """INSERT INTO tasks(task_id,case_id,case_type,owner_team,task_type,title,status,due_date,sla_hours,priority)
           VALUES('TASK-OFF-TEST-002','OFF-TEST-0002','OFFBOARDING','MANAGER','HANDOVER','Team handover','READY','2026-10-30',48,'HIGH')"""
    )
    c.commit()
    actor = {"user_id": "USR-MGR-TEST", "app_role": "MANAGER"}
    offboarding.complete_owned_task(c, "TASK-OFF-TEST-002", "MANAGER", actor, "Handover completed")
    assert c.execute("SELECT status FROM tasks WHERE task_id='TASK-OFF-TEST-002'").fetchone()[0] == "DONE"
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE entity_id='TASK-OFF-TEST-002' AND action='OFFBOARDING_TASK_COMPLETED'").fetchone()[0] == 1
    c.execute("UPDATE access_grants SET status='REVOKED' WHERE employee_id=?", (employee,))
    c.execute("UPDATE asset_assignments SET status='RECOVERED' WHERE employee_id=?", (employee,))
    c.commit()
    hr_actor = {"user_id": "USR-HR-TEST", "app_role": "HR"}
    offboarding.close_case(c, "OFF-TEST-0002", hr_actor, "All exit controls verified")
    assert c.execute("SELECT status FROM offboarding_cases WHERE offboarding_id='OFF-TEST-0002'").fetchone()[0] == "CLOSED"
    c.close()
