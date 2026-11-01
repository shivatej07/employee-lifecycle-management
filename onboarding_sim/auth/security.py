from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
_hasher=PasswordHasher()
def hash_password(password): return _hasher.hash(password)
def verify_password(encoded,password):
    try: return _hasher.verify(encoded,password)
    except VerifyMismatchError: return False
def validate_password(password,email):
    return len(password)>=10 and password.lower()!=email.lower() and any(c.islower() for c in password) and any(c.isupper() for c in password) and any(c.isdigit() for c in password) and any(not c.isalnum() for c in password)
