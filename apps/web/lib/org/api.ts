/**
 * Thin, typed wrappers around the generated organisations client
 * (@keel/api-client, from packages/api-client/src/generated/identity.query.ts —
 * see orval.config.ts). Every function below calls straight through to a
 * generated fetch function; nothing here reimplements transport, auth, or
 * error handling (identityFetch already does all three — see
 * packages/api-client/src/http/mutator.ts).
 *
 * The only thing this file adds is the request/response typing that
 * drf-spectacular could not produce for a handful of endpoints — see
 * ./types.ts's docstring for exactly why and which ones. Each such call
 * passes its body through the generated function's `options` parameter
 * (every generated fetch function accepts one) rather than bypassing the
 * generated function, so the transport, base URL, and CSRF handling are
 * still exactly what regeneration produces.
 */

import {
  meRetrieve,
  organizationsAuditList,
  organizationsCreate as generatedOrganizationsCreate,
  organizationsDestroy,
  organizationsInvitationsCreate as generatedOrganizationsInvitationsCreate,
  organizationsInvitationsDestroy,
  organizationsInvitationsList,
  organizationsList,
  organizationsMembersDestroy,
  organizationsMembersList,
  organizationsMembersPartialUpdate as generatedOrganizationsMembersPartialUpdate,
  organizationsPartialUpdate as generatedOrganizationsPartialUpdate,
  organizationsRolesList,
  organizationsTransferCreate as generatedOrganizationsTransferCreate,
  permissionsRetrieve as generatedPermissionsRetrieve,
  inviteRetrieve as generatedInviteRetrieve,
  inviteCreate as generatedInviteCreate,
  type AuditLog,
  type Invitation,
  type Membership,
  type Organization,
} from "@keel/api-client";

import type {
  InvitationCreateBody,
  InviteAcceptResponse,
  InviteResolveResponse,
  MembershipRoleUpdateBody,
  MeResponse,
  OrganizationCreateBody,
  OrganizationUpdateBody,
  PermissionsRegistryResponse,
  RoleWithPermissions,
  TransferBody,
} from "./types";

function withJsonBody(body: unknown): RequestInit {
  return {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export async function getMe(): Promise<MeResponse> {
  const result = await meRetrieve();
  return result.data as unknown as MeResponse;
}

export async function listOrganizations(): Promise<Organization[]> {
  const result = await organizationsList();
  return result.data.results;
}

export async function createOrganization(body: OrganizationCreateBody): Promise<Organization> {
  const result = await generatedOrganizationsCreate(body as never);
  return result.data;
}

export async function updateOrganization(
  slug: string,
  body: OrganizationUpdateBody,
): Promise<void> {
  await generatedOrganizationsPartialUpdate(slug, withJsonBody(body));
}

export async function deleteOrganization(slug: string): Promise<void> {
  await organizationsDestroy(slug);
}

export async function transferOwnership(slug: string, body: TransferBody): Promise<Membership> {
  const result = await generatedOrganizationsTransferCreate(slug, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return result.data as unknown as Membership;
}

export async function listMembers(slug: string): Promise<Membership[]> {
  const result = await organizationsMembersList(slug);
  return result.data.results;
}

function cursorFromNextUrl(next: string | null | undefined): string | null {
  if (!next) return null;
  try {
    return new URL(next).searchParams.get("cursor");
  } catch {
    // next is a relative path in some environments (no scheme/host to
    // resolve against) — URLSearchParams on the query string alone.
    const query = next.split("?")[1] ?? "";
    return new URLSearchParams(query).get("cursor");
  }
}

export async function listAuditLogs(
  slug: string,
  cursor?: string,
): Promise<{ results: AuditLog[]; next: string | null }> {
  const result = await organizationsAuditList(slug, cursor ? { cursor } : undefined);
  return { results: result.data.results, next: cursorFromNextUrl(result.data.next) };
}

export async function updateMemberRole(
  slug: string,
  membershipId: string,
  body: MembershipRoleUpdateBody,
): Promise<Membership> {
  const result = await generatedOrganizationsMembersPartialUpdate(
    slug,
    membershipId,
    body as never,
  );
  return result.data;
}

export async function removeMember(slug: string, membershipId: string): Promise<void> {
  await organizationsMembersDestroy(slug, membershipId);
}

export async function listInvitations(slug: string): Promise<Invitation[]> {
  const result = await organizationsInvitationsList(slug);
  return result.data.results;
}

export async function createInvitation(
  slug: string,
  body: InvitationCreateBody,
): Promise<Invitation> {
  const result = await generatedOrganizationsInvitationsCreate(slug, body as never);
  return result.data;
}

export async function revokeInvitation(slug: string, invitationId: string): Promise<void> {
  await organizationsInvitationsDestroy(slug, invitationId);
}

export async function listRoles(slug: string): Promise<RoleWithPermissions[]> {
  const result = await organizationsRolesList(slug);
  return result.data.results as RoleWithPermissions[];
}

export async function getPermissionsRegistry(): Promise<PermissionsRegistryResponse> {
  const result = await generatedPermissionsRetrieve();
  return result.data as unknown as PermissionsRegistryResponse;
}

export async function resolveInvitation(token: string): Promise<InviteResolveResponse> {
  const result = await generatedInviteRetrieve(token);
  return result.data as unknown as InviteResolveResponse;
}

export async function acceptInvitation(token: string): Promise<InviteAcceptResponse> {
  const result = await generatedInviteCreate(token);
  return result.data as unknown as InviteAcceptResponse;
}
