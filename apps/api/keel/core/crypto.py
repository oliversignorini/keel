"""The encryption seam for ``Connection`` tokens (PRD, "Third-party OAuth
connections"): ``access_token`` / ``refresh_token`` are encrypted at rest,
backed by an environment key today, upgradeable to KMS. Every call site
only ever imports ``encrypt`` / ``decrypt`` from this module, so a KMS
backend replaces the body of both functions without touching call sites.

Fernet (AES-128-CBC + HMAC) is used because it authenticates as well as
encrypts: a wrong key or corrupted ciphertext raises rather than quietly
decrypting to garbage, which is the property "fails loudly" requires.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    """Raised when ``decrypt`` is given ciphertext it cannot decrypt —
    wrong key, corrupted data, or a tampering attempt."""


def _fernet() -> Fernet:
    key = getattr(settings, "KEEL_ENCRYPTION_KEY", None)
    if not key:
        raise ImproperlyConfigured(
            "settings.KEEL_ENCRYPTION_KEY is not configured. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and set it in .env.'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt value: wrong key, corrupted ciphertext, or tampering."
        ) from exc
