Wire up a new third-party OAuth provider named in `$ARGUMENTS` (e.g.
`slack`, `quickbooks`) using the existing `keel/connections/` app —
`Connection` is already org-scoped, encrypted-at-rest, and generic across
providers. **Do not** create a new model or app for this; a new
connection is new provider glue around the existing `Connection` row.

**Ask first** for the provider's OAuth details if not given: authorize
URL, token URL, scopes needed, and whether it uses standard OAuth2
authorization-code flow or something provider-specific.

1. **Provider adapter** — `keel/connections/providers/<provider>.py`
   (create the `providers/` package if this is the first one): functions
   for building the authorize URL, exchanging the code for tokens, and
   refreshing an expired token. Keep provider-specific HTTP calls here,
   not in `services.py`.
2. **`services.py`** (create if this is the first connection wired up) —
   `connect_<provider>(organization, user, code)`,
   `disconnect_<provider>(connection)`, `refresh_<provider>_token(connection)`.
   Encrypt `access_token`/`refresh_token` with `keel.core.crypto.encrypt`
   before saving, decrypt with `.decrypt` only at the point of use — never
   log a decrypted token. `@audited("connection.created")` /
   `@not_audited(reason=...)` on every mutating function, same as any
   other service.
3. **`selectors.py`** — `list_connections(organization)`,
   `get_connection(organization, id)`. Never return `access_token` /
   `refresh_token` from a selector used by a serializer — see step 4.
4. **`serializers.py`** — the read serializer excludes both token fields
   entirely, mirroring `connections/admin.py`'s existing exclusion.
5. **`views.py`** — `ConnectionViewSet(OrgScopedViewSet)`,
   `organization_scoped = True`, `test_factory` set. OAuth callback is a
   separate thin view (not part of the CRUD viewset) that calls
   `services.connect_<provider>`.
6. **`permissions.py`** — reuse `Perm.CONNECTIONS_VIEW` /
   `Perm.CONNECTIONS_MANAGE` if they exist; otherwise run
   `/new-permission` for both first.
7. **Token refresh** — if the provider's tokens expire, add a Tier-1 task
   (`tasks.py`, `keel.core.tasks`) on the `external` queue that calls
   `refresh_<provider>_token`, scheduled per `Connection.expires_at`.

## Tests

- Mock the provider's HTTP calls (`responses` or `moto`-style fixture,
  matching `keel/files/`'s pattern for third-party clients — PRD §4's
  60% adapter coverage floor applies here).
- Assert a decrypted token is never present in a serialized response or
  a log line.
- Allow/deny tests for the viewset per invariant 2.

## Finish

`/check-invariants`.
