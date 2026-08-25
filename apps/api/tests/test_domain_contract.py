"""Closes a hole in the keel.domain import-linter contract.

apps/api/pyproject.toml's "keel.domain is independent" contract uses
source_modules = ["keel.domain.**"] rather than the literal "keel.domain"
(see the comment there for why: a literal name that doesn't exist yet
makes import-linter raise instead of passing silently). But "keel.domain.**"
only matches *submodules* of keel.domain — it does not match the
keel.domain module itself. A rule written directly in
keel/domain/__init__.py would import Django, Celery, or anything else
freely, and import-linter would stay KEPT.

This test closes that hole: keel/domain/__init__.py must contain nothing
but comments and whitespace. Put rules in a submodule instead, e.g.
keel/domain/pricing.py, where the wildcard contract actually reaches them.
"""

import ast
from pathlib import Path

DOMAIN_INIT_PATH = Path(__file__).resolve().parent.parent / "keel" / "domain" / "__init__.py"


def test_domain_init_has_no_code() -> None:
    if not DOMAIN_INIT_PATH.exists():
        return  # the import-linter contract is inert while keel/domain/ is absent

    source = DOMAIN_INIT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DOMAIN_INIT_PATH))

    assert not tree.body, (
        "keel/domain/__init__.py must contain only comments and whitespace. "
        "The import-linter contract's source_modules ('keel.domain.**') "
        "matches submodules of keel.domain, not keel.domain itself, so code "
        "written directly in this file would import Django/Celery/config "
        "freely without ever tripping that contract. Move rules into a "
        "submodule instead, e.g. keel/domain/pricing.py."
    )
