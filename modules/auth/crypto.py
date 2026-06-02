import os
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.environ.get("MASTER_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "MASTER_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
