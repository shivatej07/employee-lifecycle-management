import sqlite3
from pathlib import Path
from contextlib import contextmanager
from onboarding_sim.config import DB
SCHEMA=Path(__file__).with_name("schema.sql")
def connect(path=None):
    p=Path(path or DB); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p,timeout=30); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA journal_mode=WAL")
    return c
def initialize(path=None):
    c=connect(path); c.executescript(SCHEMA.read_text(encoding="utf-8")); c.commit(); return c
@contextmanager
def transaction(conn):
    try:
        conn.execute("BEGIN IMMEDIATE"); yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
