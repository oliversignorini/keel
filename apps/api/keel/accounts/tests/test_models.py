import pytest

from keel.accounts.models import User


def test_user_username_field_is_email() -> None:
    assert User.USERNAME_FIELD == "email"


def test_user_has_no_required_fields_beyond_email() -> None:
    assert User.REQUIRED_FIELDS == []


def test_email_field_is_unique() -> None:
    field = User._meta.get_field("email")

    assert field.unique is True


@pytest.mark.django_db
def test_create_user_hashes_the_password_and_sets_defaults() -> None:
    user = User.objects.create_user(email="ada@example.com", password="s3cret-pass")

    assert user.email == "ada@example.com"
    assert user.check_password("s3cret-pass")
    assert user.password != "s3cret-pass"
    assert user.is_staff is False
    assert user.is_active is True


@pytest.mark.django_db
def test_create_user_normalizes_email_domain_case() -> None:
    user = User.objects.create_user(email="ada@EXAMPLE.COM", password="s3cret-pass")

    assert user.email == "ada@example.com"


@pytest.mark.django_db
def test_create_user_without_email_raises() -> None:
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="s3cret-pass")


@pytest.mark.django_db
def test_create_superuser_sets_staff_and_superuser() -> None:
    user = User.objects.create_superuser(email="admin@example.com", password="s3cret-pass")

    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.django_db
def test_str_is_the_email() -> None:
    user = User.objects.create_user(email="ada@example.com", password="s3cret-pass")

    assert str(user) == "ada@example.com"
