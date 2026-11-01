# Build 08 — Authentication and Session Hardening

## Implemented
- Five consecutive invalid-password attempts lock an active account for 15 minutes.
- Locked accounts are rejected even when the correct password is supplied before lock expiry.
- Successful authentication resets the failed-attempt counter and clears expired lock state.
- Successful and failed authentication events are written to the append-only audit event table.
- Successful login records `last_login_at`.
- Session idle timeout is enforced at 30 minutes when an authenticated request is made; expired sessions are cleared and the user is redirected by protected routes.
- Login responses do not reveal whether an email exists or whether a password alone was incorrect.
- Session cookie uses SameSite=Lax and a 30-minute max age.

## Verification
- Added tests for failed-login lockout, lockout enforcement, successful-login reset and authentication audit records.
- Full test suite in a clean writable copy: **46 passed**.

## Remaining security work
This build does not yet claim full production security. CSRF token validation across all state-changing forms, HTTPS-only secure cookie configuration for production, password reset/MFA, file-upload malware scanning, and comprehensive security review remain to be completed.
