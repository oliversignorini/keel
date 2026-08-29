"""The encryption seam for third-party OAuth ``Connection`` tokens:
``access_token`` / ``refresh_token`` are encrypted at rest,
backed by environment keys today, upgradeable to KMS. Every call site
only ever imports ``encrypt`` / ``decrypt`` / ``rotate`` from this module,
so a KMS backend replaces the body of all three without touching call
sites.

Fernet (AES-128-CBC + HMAC) is used because it authenticates as well as
encrypts: a wrong key or corrupted ciphertext raises rather than quietly
decrypting to garbage, which is the property "fails loudly" requires.

``MultiFernet``, not a single ``Fernet``: a single key with no
rotation path means rotating ``KEEL_ENCRYPTION_KEY`` makes every
previously-encrypted value permanently undecryptable, with no way to tell
which key wrote a given row. ``MultiFernet`` encrypts with the first key
in ``settings.KEEL_ENCRYPTION_KEYS`` and tries every key in order to
decrypt, so a rotation is "prepend the new key" rather than "lose
everything the old key wrote" — ``rotate()`` below, and
``keel.connections.management.commands.rotate_connection_tokens``, are
what actually move existing ciphertext onto the new first key.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    """Raised when ``decrypt`` is given ciphertext no configured key can
    decrypt — every key wrong, corrupted data, or a tampering attempt."""


def _keys() -> list[str]:
    keys = getattr(settings, "KEEL_ENCRYPTION_KEYS", None) or []
    return list(keys)


def _multi_fernet() -> MultiFernet:
    keys = _keys()
    if not keys:
        raise ImproperlyConfigured(
            "settings.KEEL_ENCRYPTION_KEYS is not configured. Generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and set KEEL_ENCRYPTION_KEY '
            "in .env (comma-separated for more than one, newest first)."
        )
    return MultiFernet([Fernet(key.encode() if isinstance(key, str) else key) for key in keys])


def encrypt(plaintext: str) -> str:
    """Always encrypts with the *first* configured key — ``MultiFernet``'s
    own contract."""
    return _multi_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Tries every configured key, oldest included, so ciphertext written
    before a rotation still decrypts."""
    try:
        return _multi_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt value: no configured key matches, ciphertext is "
            "corrupted, or this is a tampering attempt."
        ) from exc


def rotate(ciphertext: str) -> str:
    """Re-encrypts ``ciphertext`` under the current first key without ever
    exposing the plaintext to the caller — ``MultiFernet.rotate``'s own
    guarantee. A no-op (ciphertext unchanged) if it was already encrypted
    with the first key. Raises ``DecryptionError`` under the same
    condition ``decrypt`` does; a caller iterating many rows should treat
    that as "this row's key predates every configured key" rather than
    aborting the whole rotation."""
    try:
        return _multi_fernet().rotate(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not rotate value: no configured key matches, ciphertext is "
            "corrupted, or this is a tampering attempt."
        ) from exc
