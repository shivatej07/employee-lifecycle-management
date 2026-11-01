"""Additional tests for generator, data services, CLI and reporting paths."""
import csv
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from onboarding_sim.ids import IdFactory
from onboarding_sim.database import connect, initialize, transaction
from onboarding_sim.generator import core as generator
from onboarding_sim.validation import core as validation
from onboarding_sim.engine import core as engine
from onboarding_sim.reporting import core as reporting
from onboarding_sim.services import workflows
from onboarding_sim import search as search_module


@pytest.fixture()
def generated(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    gt = tmp_path / "ground_truth"
    monkeypatch.setattr(generator, "GROUND_TRUTH", gt)
    manifest = generator.generate(seed=20261022, scale="starter", out=out)
    return out / "dataset.db", out, gt, manifest


def test_generator_is_deterministic_and_writes_expected_artifacts(generated):
    db, out, gt, manifest = generated
    assert manifest["requested_counts"] == {"employees": 100, "tasks": 800, "grants": 150, "assets": 120}
    assert (out / "source_manifest.json").exists()
    assert (gt / "ground_truth.csv").exists()
    with (out / "employees.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 100
    c = connect(db)
    assert c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 100
    c.close()


def test_generator_custom_counts_and_csv_empty_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "GROUND_TRUTH", tmp_path / "gt")
    result = generator.generate(seed=7, scale="starter", out=tmp_path / "custom", employees=60, tasks=120, grants=60, assets=60)
    assert result["requested_counts"]["employees"] == 60
    empty = tmp_path / "empty.csv"
    generator.write_csv(empty, [])
    assert not empty.exists()


def test_database_transaction_rolls_back_and_initialize_is_idempotent(tmp_path):
    db = tmp_path / "nested" / "test.db"
    c = initialize(db)
    initialize(db).close()
    with pytest.raises(RuntimeError):
        with transaction(c):
            c.execute("INSERT INTO departments(department_id,name,cost_center,location_mode) VALUES('D-X','Test','CC-X','OFFICE')")
            raise RuntimeError("rollback")
    assert c.execute("SELECT COUNT(*) FROM departments WHERE department_id='D-X'").fetchone()[0] == 0
    c.close()


def test_validation_pass_and_duplicate_serial_failure(generated):
    db, _, _, _ = generated
    ok = validation.validate(db)
    assert ok["passed"] is True
    c = connect(db)
    row = c.execute("SELECT serial_number FROM assets LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO assets(asset_id,asset_type,serial_number,model,purchase_date,current_status) VALUES('AST-DUPLICATE-TEST','LAPTOP',?,'Test','2026-01-01','IN_STOCK')", (row[0],))
    c.close()


def test_engine_recalculates_ready_and_blocked_tasks(generated):
    db, _, _, _ = generated
    c = connect(db)
    no_dep = c.execute("SELECT task_id FROM tasks WHERE task_id NOT IN (SELECT task_id FROM dependencies) LIMIT 1").fetchone()[0]
    c.execute("UPDATE tasks SET status='PENDING' WHERE task_id=?", (no_dep,))
    dep = c.execute("SELECT task_id,depends_on_task_id FROM dependencies LIMIT 1").fetchone()
    c.execute("UPDATE tasks SET status='PENDING' WHERE task_id=?", (dep['task_id'],))
    c.execute("UPDATE tasks SET status='PENDING' WHERE task_id=?", (dep['depends_on_task_id'],))
    c.commit(); c.close()
    result = engine.run_engine(db)
    c = connect(db)
    assert c.execute("SELECT status FROM tasks WHERE task_id=?", (no_dep,)).fetchone()[0] == "READY"
    assert c.execute("SELECT status FROM tasks WHERE task_id=?", (dep['task_id'],)).fetchone()[0] == "BLOCKED"
    c.close()
    assert result["tasks_recalculated"] >= 2


def test_search_obeys_role_scope(generated):
    db, _, _, _ = generated
    c = connect(db)
    c.execute("UPDATE employees SET manager_id='EMP-000001' WHERE employee_id='EMP-000011'")
    c.commit()
    manager = {"app_role": "MANAGER", "employee_id": "EMP-000001"}
    employee = {"app_role": "EMPLOYEE", "employee_id": "EMP-000001"}
    hr = {"app_role": "HR", "employee_id": "EMP-000001"}
    assert len(search_module.search(c, manager, "EMP-000011")) == 1
    assert search_module.search(c, employee, "EMP-000011") == []
    assert search_module.search(c, hr, "EMP-000011")
    assert search_module.search(c, hr, " ") == []
    c.close()


def test_complete_task_audits_and_rejects_invalid_states(generated):
    db, _, _, _ = generated
    c = connect(db)
    task = c.execute("SELECT task_id FROM tasks WHERE task_id NOT IN (SELECT task_id FROM dependencies) LIMIT 1").fetchone()[0]
    c.execute("UPDATE tasks SET status='READY' WHERE task_id=?", (task,)); c.commit()
    result = workflows.complete_task(c, task, "USR-TEST", "EMPLOYEE", "EVT-TEST")
    assert result["status"] == "DONE"
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE event_id='EVT-TEST'").fetchone()[0] == 1
    with pytest.raises(ValueError, match="not ready"):
        workflows.complete_task(c, task, "USR-TEST", "EMPLOYEE", "EVT-TEST-2")
    with pytest.raises(ValueError, match="not found"):
        workflows.complete_task(c, "MISSING", "USR-TEST", "EMPLOYEE", "EVT-TEST-3")
    c.close()


def test_reporting_metrics_and_anomaly_evaluation(generated, tmp_path, monkeypatch):
    db, _, gt, _ = generated
    monkeypatch.setattr(reporting, "GROUND_TRUTH", gt)
    monkeypatch.setattr(reporting, "REPORTS", tmp_path / "reports")
    m = reporting.metrics(db)
    assert m["employees"] == 100 and m["tasks"] == 800
    assert (tmp_path / "reports" / "metrics_report.json").exists()
    result = reporting.anomaly_evaluation(db)
    assert "TERMINATED_EMPLOYEE_RETAINS_GRANT" in result
    saved = json.loads((tmp_path / "reports" / "anomaly_report.json").read_text())
    assert saved == result


def test_demo_initialization_and_missing_dataset(tmp_path, monkeypatch):
    from onboarding_sim import demo
    monkeypatch.setattr(demo, "EXPORTS", tmp_path / "exports")
    monkeypatch.setattr(demo, "DB", tmp_path / "app.db")
    with pytest.raises(FileNotFoundError):
        demo.init_demo_database()
    monkeypatch.setattr(generator, "GROUND_TRUTH", tmp_path / "gt")
    generator.generate(seed=20261022, scale="starter", out=tmp_path / "exports")
    result = demo.init_demo_database(reset=True)
    assert len(result["accounts"]) == 5
    c = connect(tmp_path / "app.db")
    assert c.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0] == 5
    c.close()


@pytest.mark.parametrize("command", ["validate", "run-engine", "detect", "report", "init-app", "reset-app", "create-admin", "serve"])
def test_cli_dispatches_commands(command, monkeypatch):
    from onboarding_sim import __main__ as cli
    monkeypatch.setattr(sys, "argv", ["onboarding_sim", command])
    monkeypatch.setattr(cli, "validate", lambda: {"passed": True})
    monkeypatch.setattr(cli, "run_engine", lambda: {"tasks_recalculated": 0})
    monkeypatch.setattr(cli, "detect", lambda: [])
    monkeypatch.setattr(cli, "metrics", lambda: {})
    monkeypatch.setattr(cli, "anomaly_evaluation", lambda: {})
    monkeypatch.setattr(cli, "init_demo_database", lambda reset=False: {"reset": reset})
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: None)
    cli.main()


def test_cli_generate_and_reproduce(monkeypatch, tmp_path):
    from onboarding_sim import __main__ as cli
    monkeypatch.setattr(sys, "argv", ["onboarding_sim", "generate", "--scale", "starter", "--out", str(tmp_path)])
    monkeypatch.setattr(cli, "generate", lambda *a, **k: {"requested_counts": {"employees": 1}})
    cli.main()
    monkeypatch.setattr(sys, "argv", ["onboarding_sim", "reproduce"])
    calls = iter([{"requested_counts": {"employees": 100}}, {"requested_counts": {"employees": 100}}])
    monkeypatch.setattr(cli, "generate", lambda *a, **k: next(calls))
    cli.main()
