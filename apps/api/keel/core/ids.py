"""UUIDv7 primary keys (PRD §7 conventions, v1.2 manifest note).

``uuid.uuid7`` lands in the standard library in Python 3.14; the floor here
is 3.12, so generation is wrapped behind ``uuid_utils`` and converted to a
stdlib ``uuid.UUID``. When the floor moves to 3.14+, this becomes a one-line
change to ``return uuid.uuid7()`` and every call site is untouched.

UUIDv7 is chosen over UUIDv4 for one property: values sort in creation
order, because the high bits are a millisecond timestamp. That keeps
b-tree indexes on primary keys append-mostly instead of randomly
scattered, which is the whole reason to prefer it over v4 for a PK.
"""

import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a stdlib ``uuid.UUID``."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
