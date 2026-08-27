/**
 * Thin, typed wrappers around the generated organisations client
 * (@keel/api-client, from packages/api-client/src/generated/identity.query.ts —
 * see orval.config.ts). Every function below calls straight through to a
 * generated fetch function; nothing here reimplements transport, auth, or
 * error handling (identityFetch already does all three — see
 * packages/api-client/src/http/mutator.ts).
 *
 * ./types.ts's docstring covers the small set of aliases this file
 * imports under an org/ name rather than the generated one directly.
 */

import {
  unwrapData,
  retrieveMe as generatedRetrieveMe,
  listAuditLogs as generatedListAuditLogs,
  createOrganization as generatedCreateOrganization,
  deleteOrganization as generatedDeleteOrganization,
  createInvitation as generatedCreateInvitation,
  deleteInvitation as generatedDeleteInvitation,
  listInvitations as generatedListInvitations,
  listOrganizations as generatedListOrganizations,
  deleteMember as generatedDeleteMember,
  listMembers as generatedListMembers,
  updateMemberRole as generatedUpdateMemberRole,
  updateOrganization as generatedUpdateOrganization,
  listRoles as generatedListRoles,
  transferOrganization as generatedTransferOrganization,
  retrievePermissionCodes as generatedRetrievePermissionCodes,
  retrieveInvite as generatedRetrieveInvite,
  acceptInvite as generatedAcceptInvite,
  type AuditLogOut,
  type InvitationCreateIn,
  type InvitationOut,
  type MembershipOut,
  type MembershipRoleUpdateIn,
  type OrganizationCreateIn,
  type OrganizationOut,
  type OrganizationUpdateIn,
  type PermissionCodesOut,
  type TransferIn,
} from "@keel/api-client";

import type { InviteResolveResponse, MeResponse, RoleWithPermissions } from "./types";

export async function getMe(): Promise<MeResponse> {
  const result = await generatedRetrieveMe();
  return unwrapData(result);
}

export async function listOrganizations(): Promise<OrganizationOut[]> {
  const result = await generatedListOrganizations();
  return unwrapData(result).results;
}

export async function createOrganization(body: OrganizationCreateIn): Promise<OrganizationOut> {
  const result = await generatedCreateOrganization(body);
  return unwrapData(result);
}

export async function updateOrganization(slug: string, body: OrganizationUpdateIn): Promise<void> {
  await generatedUpdateOrganization(slug, body);
}

export async function deleteOrganization(slug: string): Promise<void> {
  await generatedDeleteOrganization(slug);
}

export async function transferOwnership(slug: string, body: TransferIn): Promise<MembershipOut> {
  const result = await generatedTransferOrganization(slug, body);
  return unwrapData(result);
}

export async function listMembers(slug: string): Promise<MembershipOut[]> {
  const result = await generatedListMembers(slug);
  return unwrapData(result).results;
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
): Promise<{ results: AuditLogOut[]; next: string | null }> {
  const data = unwrapData(await generatedListAuditLogs(slug, cursor ? { cursor } : undefined));
  return { results: data.results, next: cursorFromNextUrl(data.next) };
}

export async function updateMemberRole(
  slug: string,
  membershipId: string,
  body: MembershipRoleUpdateIn,
): Promise<MembershipOut> {
  const result = await generatedUpdateMemberRole(slug, membershipId, body);
  return unwrapData(result);
}

export async function removeMember(slug: string, membershipId: string): Promise<void> {
  await generatedDeleteMember(slug, membershipId);
}

export async function listInvitations(slug: string): Promise<InvitationOut[]> {
  const result = await generatedListInvitations(slug);
  return unwrapData(result).results;
}

export async function createInvitation(
  slug: string,
  body: InvitationCreateIn,
): Promise<InvitationOut> {
  const result = await generatedCreateInvitation(slug, body);
  return unwrapData(result);
}

export async function revokeInvitation(slug: string, invitationId: string): Promise<void> {
  await generatedDeleteInvitation(slug, invitationId);
}

export async function listRoles(slug: string): Promise<RoleWithPermissions[]> {
  const result = await generatedListRoles(slug);
  return unwrapData(result).results;
}

export async function getPermissionsRegistry(): Promise<PermissionCodesOut> {
  const result = await generatedRetrievePermissionCodes();
  return unwrapData(result);
}

export async function resolveInvitation(token: string): Promise<InviteResolveResponse> {
  const result = await generatedRetrieveInvite(token);
  return unwrapData(result);
}

export async function acceptInvitation(token: string): Promise<MembershipOut> {
  const result = await generatedAcceptInvite(token);
  return unwrapData(result);
}
