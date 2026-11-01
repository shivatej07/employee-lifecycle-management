# Build 09 — Employee Document Management and HR Verification

## Employee features
- Upload categorized identity, address, education, tax, contract, and other documents.
- Accepted formats: PDF, PNG, JPG, JPEG, DOCX.
- Maximum upload size: 5 MB.
- File extension, declared content type, and basic file signature are checked.
- Employee dashboard lists their own uploaded documents and HR review status.
- Upload success and validation feedback are shown on the employee dashboard.

## HR features
- HR document review queue at `/hr/documents`.
- HR can download submitted documents through an authenticated HR-only route.
- HR can verify or reject pending documents.
- A review note is mandatory for either decision.
- Reviewed documents cannot be reviewed a second time.
- HR dashboard links to the document verification queue.

## Storage and audit
- Document metadata is stored in SQLite `employee_documents`.
- File bytes are stored outside the static web directory under `data/private_documents`.
- Stored filenames are random UUIDs; original filenames are retained only as display/download metadata.
- Upload and review actions create audit events.
- HR receives upload notifications; the employee receives the review decision notification.
- A failed database insert removes the newly written file.

## Routes
- Employee upload: `POST /employee/documents`
- HR queue: `GET /hr/documents`
- HR download: `GET /hr/documents/{document_id}/download`
- HR review: `POST /hr/documents/{document_id}/review`

## Verification
Run `python -m onboarding_sim reset-app` before `python -m pytest -q` in a clean checkout.
Build 09 test result: **49 passed**.

## Security limitations
- File signature checks are basic validation, not antivirus/malware scanning.
- Production deployments should store files in a private object store, enforce HTTPS, and add malware scanning and a retention policy.
- CSRF validation is not yet applied consistently to every form.
