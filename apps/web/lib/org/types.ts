/**
 * Thin aliases onto the generated organisations client types
 * (@keel/api-client, from packages/api-client/src/generated/identity.query.ts —
 * see orval.config.ts).
 *
 * The DRF -> Django Ninja migration gave `/me/`, `/permissions/`,
 * `/invite/{token}/` and every request body a real, generated schema —
 * the hand-transcribed duplicates this file used to carry existed only
 * because drf-spectacular could not type a plain `APIView` with no
 * `serializer_class`, or a serializer swapped in at request time. Ninja's
 * Pydantic schemas (`keel.organizations.schemas`) don't have that gap, so
 * everything of that shape was deleted here; `pnpm generate` produces it
 * directly under `@keel/api-client`.
 *
 * What remains are call-site-friendly aliases for the handful of shapes
 * existing code still imports under an org/ name rather than the
 * generated one directly.
 */

import type { InviteDetailOut, MeOrganizationOut, MeOut, RoleOut } from "@keel/api-client";

export type MeOrganization = MeOrganizationOut;
export type MeResponse = MeOut;
export type InviteResolveResponse = InviteDetailOut;

/** `Role.permissions` is already typed `string[]` by the generated
 * schema (Ninja's `RoleOut.permissions: list[str]`, not a Postgres
 * JSONField the generator can only call `unknown`) — this alias exists so
 * existing call sites don't need to change; new code should import
 * `RoleOut` from `@keel/api-client` directly. */
export type RoleWithPermissions = RoleOut;
