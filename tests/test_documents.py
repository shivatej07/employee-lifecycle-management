import pytest
from onboarding_sim.database import connect
from onboarding_sim.generator.core import generate
from onboarding_sim.services import documents


@pytest.fixture
def document_db(tmp_path, monkeypatch):
    out = tmp_path / "exports"
    generate(seed=20261022, scale="starter", out=out)
    db = out / "dataset.db"
    c = connect(db)
    employee = c.execute("SELECT employee_id FROM employees WHERE employment_status!='TERMINATED' ORDER BY employee_id LIMIT 1").fetchone()[0]
    monkeypatch.setattr(documents, "STORAGE_DIR", tmp_path / "private_docs")
    yield c, employee
    c.close()


def test_upload_valid_pdf_and_hr_verification(document_db):
    c, employee = document_db
    employee_actor = {"user_id":"USR-EMP-1","app_role":"EMPLOYEE","document_type":"IDENTITY"}
    document_id = documents.upload_document(
        c, employee, employee_actor, "identity.pdf", "application/pdf",
        b"%PDF-1.7\\nsmall test document"
    )
    row = c.execute("SELECT * FROM employee_documents WHERE document_id=?", (document_id,)).fetchone()
    assert row["status"] == "PENDING_REVIEW"
    assert row["file_size"] > 0
    assert documents.document_file_path(c, document_id).is_file()
    hr_actor = {"user_id":"USR-HR-1","app_role":"HR"}
    documents.review_document(c, document_id, hr_actor, "VERIFIED", "Identity details checked.")
    row = c.execute("SELECT status,review_note,reviewed_by FROM employee_documents WHERE document_id=?", (document_id,)).fetchone()
    assert row["status"] == "VERIFIED"
    assert row["review_note"] == "Identity details checked."
    assert row["reviewed_by"] == "USR-HR-1"
    assert c.execute("SELECT COUNT(*) FROM audit_events WHERE entity_id=? AND action IN ('DOCUMENT_UPLOADED','DOCUMENT_REVIEWED')", (document_id,)).fetchone()[0] == 2


def test_reject_wrong_signature_and_oversize_files(document_db):
    c, employee = document_db
    actor = {"user_id":"USR-EMP-1","app_role":"EMPLOYEE","document_type":"OTHER"}
    with pytest.raises(ValueError, match="does not match"):
        documents.upload_document(c, employee, actor, "fake.pdf", "application/pdf", b"not a pdf")
    with pytest.raises(ValueError, match="5 MB"):
        documents.upload_document(c, employee, actor, "large.pdf", "application/pdf", b"%PDF-" + b"x" * documents.MAX_FILE_SIZE)


def test_reject_review_without_note_or_repeated_review(document_db):
    c, employee = document_db
    actor = {"user_id":"USR-EMP-1","app_role":"EMPLOYEE","document_type":"EDUCATION"}
    did = documents.upload_document(c, employee, actor, "degree.pdf", "application/pdf", b"%PDF-1.4 test")
    hr = {"user_id":"USR-HR-1","app_role":"HR"}
    with pytest.raises(ValueError, match="review note"):
        documents.review_document(c, did, hr, "REJECTED", " ")
    documents.review_document(c, did, hr, "REJECTED", "Unreadable scan; please upload again.")
    with pytest.raises(ValueError, match="Only pending"):
        documents.review_document(c, did, hr, "VERIFIED", "Second review")
