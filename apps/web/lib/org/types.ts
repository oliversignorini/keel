/**
 * Hand-written types for the organisations API surface that
 * `packages/api-client`'s generation cannot type correctly from the live
 * spec (regenerated at packages/api-client/openapi.merged.json via
 * scripts/merge_openapi.py — see orval.config.ts's `orgTags`).
 *
 * (See packages/api-client/orval.config.ts for why organisations and
 * allauth share one generated output pair rather than two.)
 *
 * Two distinct gaps, both inside apps/api/keel/organizations/viewsets.py,
 * which this worktree does not own and must not edit (a concurrent
 * worktree is building billing there):
 *
 * 1. `MeView`, `OrganizationDetailView`, `OrganizationTransferView`,
 *    `PermissionsRegistryView` and `InvitationAcceptView` are plain
 *    `APIView`s with no `serializer_class`, so drf-spectacular emits no
 *    response schema at all for them — orval generates `data: void`.
 * 2. `InvitationViewSet.create()` and `MembershipViewSet.update()` swap in
 *    a narrower serializer at request time (`InvitationCreateSerializer`,
 *    `MembershipRoleUpdateSerializer`) that the *declared*
 *    `serializer_class` used for schema generation never sees, so orval's
 *    request-body type is derived from the wrong (fully read-only) model
 *    serializer and comes out empty.
 *
 * Every shape below is transcribed from the actual serializer/view source
 * (apps/api/keel/organizations/{viewsets,serializers}.py) rather than
 * guessed, and is narrower than "unknown" everywhere it can be. Delete a
 * given type here the moment the corresponding view grows a real
 * `serializer_class` and `pnpm generate` produces it directly.
 */

import type { Membership, Role } from "@keel/api-client";

/** `Role.permissions` is a Postgres JSONField; drf-spectacular can only
 * say `unknown`. It is always a flat list of permission codes
 * (organizations/models.py `Role.permissions`). */
export interface RoleWithPermissions extends Omit<Role, "permissions"> {
  permissions: string[];
}

export interface MeOrganization {
  id: string;
  slug: string;
  name: string;
  role: string | null;
  permissions: string[];
  entitlements: Record<string, unknown>;
}

/** `GET /api/v1/me/` (MeView.get) — PRD §7: "the single endpoint the
 * client renders from." */
export interface MeResponse {
  user: {
    id: string;
    email: string;
    name: string;
  };
  organizations: MeOrganization[];
  /** Non-null only while this session is impersonating (PRD §6
   * "Impersonation"; docs/plans/phase-8.md 8.3) — the staff user who
   * started it. Drives `<ImpersonationBanner>`. */
  impersonator: { id: string; email: string; name: string } | null;
}

/** `GET /api/v1/permissions/` (PermissionsRegistryView.get). */
export interface PermissionsRegistryResponse {
  codes: string[];
}

/** `POST /api/v1/organizations/` body (OrganizationListCreateView.create,
 * validated by OrganizationCreateSerializer). */
export interface OrganizationCreateBody {
  name: string;
  slug?: string;
}

/** `PATCH /api/v1/organizations/{slug}/` body
 * (OrganizationDetailView.patch, OrganizationUpdateSerializer). */
export interface OrganizationUpdateBody {
  name?: string;
}

/** `POST /api/v1/organizations/{slug}/transfer/` body
 * (OrganizationTransferView.post reads `membership_id` off raw request.data). */
export interface TransferBody {
  membership_id: string;
}

/** `POST /api/v1/organizations/{slug}/invitations/` body
 * (InvitationViewSet.create, InvitationCreateSerializer). */
export interface InvitationCreateBody {
  email: string;
  role_id: string;
}

/** `PATCH /api/v1/organizations/{slug}/members/{id}/` body
 * (MembershipViewSet.update, MembershipRoleUpdateSerializer). */
export interface MembershipRoleUpdateBody {
  role_id: string;
}

/** `GET /api/v1/invite/{token}/` (InvitationAcceptView.get) — the "not
 * signed in" and "signed in" resolve step (PRD §6 "Invitation"). Returns
 * 200 for a token that is neither expired, revoked, nor already accepted;
 * a 409 `invalid_or_expired` for all three of those, deliberately
 * indistinguishable (phase-3.md B.4). */
export interface InviteResolveResponse {
  organization: {
    name: string;
    slug: string;
  };
  email: string;
  requires_signup: boolean;
}

/** `POST /api/v1/invite/{token}/` (InvitationAcceptView.post) — accept.
 * Returns the new Membership, which the generated client already types
 * correctly (MembershipSerializer is a real ModelSerializer). */
export type InviteAcceptResponse = Membership;
