from cryptography.fernet import Fernet

from keel.core.crypto import DecryptionError, decrypt, encrypt


def test_round_trip(settings) -> None:
    settings.KEEL_ENCRYPTION_KEY = Fernet.generate_key().decode()

    ciphertext = encrypt("super-secret-token")

    assert ciphertext != "super-secret-token"
    assert decrypt(ciphertext) == "super-secret-token"


def test_ciphertext_is_not_the_plaintext_and_is_a_string(settings) -> None:
    settings.KEEL_ENCRYPTION_KEY = Fernet.generate_key().decode()

    ciphertext = encrypt("hello")

    assert isinstance(ciphertext, str)
    assert "hello" not in ciphertext


def test_wrong_key_fails_loudly(settings) -> None:
    settings.KEEL_ENCRYPTION_KEY = Fernet.generate_key().decode()
    ciphertext = encrypt("super-secret-token")

    settings.KEEL_ENCRYPTION_KEY = Fernet.generate_key().decode()

    try:
        decrypt(ciphertext)
    except DecryptionError:
        pass
    else:
        raise AssertionError("decrypt() with the wrong key should raise DecryptionError")


def test_corrupted_ciphertext_fails_loudly(settings) -> None:
    settings.KEEL_ENCRYPTION_KEY = Fernet.generate_key().decode()
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

    settings.KEEL_ENCRYPTION_KEY = ""

    try:
        encrypt("anything")
    except ImproperlyConfigured:
        pass
    else:
        raise AssertionError("encrypt() with no configured key should raise ImproperlyConfigured")
