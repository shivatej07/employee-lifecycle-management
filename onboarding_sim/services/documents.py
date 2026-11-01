"""Validated employee document storage and HR review workflow."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import re

from onboarding_sim.config import ROOT
from onboarding_sim.database import transaction
from onboarding_sim.services.workflows import append_audit

MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx"}
ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/zip", "application/octet-stream"},
}
DOCUMENT_TYPES = {"IDENTITY", "ADDRESS", "EDUCATION", "TAX", "CONTRACT", "OTHER"}
STORAGE_DIR = ROOT / "data" / "private_documents"


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _id(conn, table, column, prefix):
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] + 1
    while True:
        candidate = f"{prefix}{n:08d}"
        if not conn.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (candidate,)).fetchone():
            return candidate
        n += 1


def _audit(conn, actor, action, document_id, old, new, reason, now):
    append_audit(conn, _id(conn, "audit_events", "event_id", "EVT-DOC-"),
                 actor["user_id"], actor["app_role"], action, "EmployeeDocument",
                 document_id, old, new, reason, now)


def list_employee_documents(conn, employee_id):
    return conn.execute(
        "SELECT * FROM employee_documents WHERE employee_id=? ORDER BY uploaded_at DESC",
        (employee_id,),
    ).fetchall()


def upload_document(conn, employee_id, actor, filename, content_type, content):
    if not employee_id or not conn.execute(
        "SELECT 1 FROM employees WHERE employee_id=?", (employee_id,)
    ).fetchone():
        raise ValueError("Employee profile was not found.")
    original = Path(filename or "").name
    ext = Path(original).suffix.lower()
    if not original or ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Allowed formats: PDF, PNG, JPG, JPEG and DOCX.")
    if not content:
        raise ValueError("The selected file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("File exceeds the 5 MB upload limit.")
    if content_type not in ALLOWED_TYPES[ext]:
        raise ValueError("The file content type does not match the allowed format.")
    document_type = (actor.get("document_type") or "OTHER").upper()
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("Select a valid document category.")
    # Basic signature checks prevent extension-only spoofing for common formats.
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".docx": content.startswith(b"PK\x03\x04"),
    }
    if not signatures[ext]:
        raise ValueError("The uploaded file does not match its declared file format.")
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid4().hex}{ext}"
    target = STORAGE_DIR / stored
    target.write_bytes(content)
    now = _now()
    try:
        with transaction(conn):
            did = _id(conn, "employee_documents", "document_id", "DOC-")
            conn.execute(
                """INSERT INTO employee_documents(document_id,employee_id,uploaded_by,document_type,
                   original_filename,stored_filename,content_type,file_size,status,uploaded_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (did, employee_id, actor["user_id"], document_type, original, stored,
                 content_type, len(content), "PENDING_REVIEW", now),
            )
            _audit(conn, actor, "DOCUMENT_UPLOADED", did, None, "PENDING_REVIEW",
                   f"{document_type} document uploaded", now)
            conn.execute(
                """INSERT INTO notifications(notification_id,recipient_role,type,entity_type,entity_id,message,created_at)
                   VALUES(?, 'HR','DOCUMENT_UPLOADED','EmployeeDocument',?,?,?)""",
                (_id(conn, "notifications", "notification_id", "NTF-DOC-"),
                 did, f"New {document_type.lower()} document uploaded for {employee_id}.", now),
            )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return did


def review_document(conn, document_id, reviewer, decision, note):
    decision = (decision or "").upper()
    note = (note or "").strip()
    if decision not in {"VERIFIED", "REJECTED"}:
        raise ValueError("Choose verified or rejected.")
    if not note:
        raise ValueError("A review note is required.")
    row = conn.execute("SELECT * FROM employee_documents WHERE document_id=?", (document_id,)).fetchone()
    if not row:
        raise ValueError("Document not found.")
    if row["status"] != "PENDING_REVIEW":
        raise ValueError("Only pending documents can be reviewed.")
    now = _now()
    with transaction(conn):
        conn.execute(
            """UPDATE employee_documents SET status=?,review_note=?,reviewed_by=?,reviewed_at=?
               WHERE document_id=?""",
            (decision, note, reviewer["user_id"], now, document_id),
        )
        _audit(conn, reviewer, "DOCUMENT_REVIEWED", document_id, "PENDING_REVIEW",
               decision, note, now)
        conn.execute(
            """INSERT INTO notifications(notification_id,recipient_user_id,type,entity_type,entity_id,message,created_at)
               SELECT ?,u.user_id,'DOCUMENT_REVIEWED','EmployeeDocument',?,?,?
               FROM user_accounts u WHERE u.employee_id=?""",
            (_id(conn, "notifications", "notification_id", "NTF-DOC-"),
             document_id, f"Your {row['document_type'].lower()} document was {decision.lower()}: {note}",
             now, row["employee_id"]),
        )
    return True


def document_file_path(conn, document_id):
    row = conn.execute("SELECT stored_filename FROM employee_documents WHERE document_id=?", (document_id,)).fetchone()
    if not row:
        raise ValueError("Document not found.")
    path = (STORAGE_DIR / row["stored_filename"]).resolve()
    if path.parent != STORAGE_DIR.resolve() or not path.is_file():
        raise ValueError("Stored document is unavailable.")
    return path
