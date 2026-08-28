from cryptography.fernet import Fernet

from keel.core.crypto import DecryptionError, decrypt, encrypt, rotate


def test_round_trip(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

    ciphertext = encrypt("super-secret-token")

    assert ciphertext != "super-secret-token"
    assert decrypt(ciphertext) == "super-secret-token"


def test_ciphertext_is_not_the_plaintext_and_is_a_string(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

    ciphertext = encrypt("hello")

    assert isinstance(ciphertext, str)
    assert "hello" not in ciphertext


def test_wrong_key_fails_loudly(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    ciphertext = encrypt("super-secret-token")

    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

    try:
        decrypt(ciphertext)
    except DecryptionError:
        pass
    else:
        raise AssertionError("decrypt() with the wrong key should raise DecryptionError")


def test_corrupted_ciphertext_fails_loudly(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    ciphertext = encrypt("super-secret-token")

    corrupted = ciphertext[:-4] + "abcd"

    try:
        decrypt(corrupted)
    except DecryptionError:
        pass
    else:
        raise AssertionError("decrypt() of corrupted ciphertext should raise DecryptionError")


def test_missing_key_raises_improperly_configured(settings) -> None:
    from django.core.exceptions import ImproperlyConfigured

    settings.KEEL_ENCRYPTION_KEYS = []

    try:
        encrypt("anything")
    except ImproperlyConfigured:
        pass
    else:
        raise AssertionError("encrypt() with no configured key should raise ImproperlyConfigured")


# --- Key rotation -----------------------------------------------------------


def test_ciphertext_written_with_the_old_key_still_decrypts_after_rotation(settings) -> None:
    """The whole point of MultiFernet over a single Fernet: rotating the
    *first* (encrypting) key must not make previously-written ciphertext
    unreadable."""
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    ciphertext = encrypt("pre-rotation-token")

    new_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]

    assert decrypt(ciphertext) == "pre-rotation-token"


def test_encrypt_always_uses_the_first_configured_key(settings) -> None:
    new_key = Fernet.generate_key().decode()
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]

    ciphertext = encrypt("fresh-token")

    # Only the first key can decrypt a value MultiFernet just encrypted —
    # if the old key alone could too, encrypt() used the wrong key.
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    try:
        decrypt(ciphertext)
    except DecryptionError:
        pass
    else:
        raise AssertionError("encrypt() should have used the first (new) key, not the old one")


def test_rotate_moves_ciphertext_onto_the_new_first_key(settings) -> None:
    old_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [old_key]
    ciphertext = encrypt("rotate-me")

    new_key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [new_key, old_key]
    rotated = rotate(ciphertext)

    assert rotated != ciphertext
    assert decrypt(rotated) == "rotate-me"

    # Dropping the old key entirely must not break the rotated value —
    # proving it now genuinely lives under the new key alone.
    settings.KEEL_ENCRYPTION_KEYS = [new_key]
    assert decrypt(rotated) == "rotate-me"


def test_rotate_is_idempotent_when_already_under_the_first_key(settings) -> None:
    key = Fernet.generate_key().decode()
    settings.KEEL_ENCRYPTION_KEYS = [key]
    ciphertext = encrypt("already-current")

    rotated = rotate(ciphertext)

    assert decrypt(rotated) == "already-current"


def test_rotate_of_undecryptable_ciphertext_fails_loudly(settings) -> None:
    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    ciphertext = encrypt("orphaned")

    settings.KEEL_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

    try:
        rotate(ciphertext)
    except DecryptionError:
        pass
    else:
        raise AssertionError("rotate() with no matching key should raise DecryptionError")


def test_comma_separated_env_value_becomes_a_key_list(settings) -> None:
    """base.py: KEEL_ENCRYPTION_KEYS = env.list("KEEL_ENCRYPTION_KEY", ...) —
    proves the single env var, comma-separated, is what a rotation
    actually sets, not a second setting name."""
    import environ

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    env = environ.Env()
    parsed = env.parse_value(f"{new_key},{old_key}", list)

    assert parsed == [new_key, old_key]
