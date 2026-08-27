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
  me as generatedMe,
  listAuditLogs as generatedListAuditLogs,
  createOrganization as generatedCreateOrganization,
  deleteOrganization as generatedDeleteOrganization,
  createInvitation as generatedCreateInvitation,
  revokeInvitation as generatedRevokeInvitation,
  listInvitations as generatedListInvitations,
  listOrganizations as generatedListOrganizations,
  removeMember as generatedRemoveMember,
  listMembers as generatedListMembers,
  updateMemberRole as generatedUpdateMemberRole,
  updateOrganization as generatedUpdateOrganization,
  listRoles as generatedListRoles,
  transferOrganization as generatedTransferOrganization,
  permissionsRegistry as generatedPermissionsRegistry,
  inviteDetail as generatedInviteDetail,
  inviteAccept as generatedInviteAccept,
  type AuditLogOut,
  type InvitationOut,
  type MembershipOut,
  type OrganizationOut,
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

export async function getMe(): Promise<MeResponse> {
  const result = await generatedMe();
  return result.data as unknown as MeResponse;
}

export async function listOrganizations(): Promise<OrganizationOut[]> {
  const result = await generatedListOrganizations();
  return result.data.results;
}

export async function createOrganization(body: OrganizationCreateBody): Promise<OrganizationOut> {
  const result = await generatedCreateOrganization(body as never);
  return result.data;
}

export async function updateOrganization(
  slug: string,
  body: OrganizationUpdateBody,
): Promise<void> {
  await generatedUpdateOrganization(slug, body as never);
}

export async function deleteOrganization(slug: string): Promise<void> {
  await generatedDeleteOrganization(slug);
}

export async function transferOwnership(slug: string, body: TransferBody): Promise<MembershipOut> {
  const result = await generatedTransferOrganization(slug, body as never);
  return result.data as unknown as MembershipOut;
}

export async function listMembers(slug: string): Promise<MembershipOut[]> {
  const result = await generatedListMembers(slug);
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
): Promise<{ results: AuditLogOut[]; next: string | null }> {
  const result = await generatedListAuditLogs(slug, cursor ? { cursor } : undefined);
  return { results: result.data.results, next: cursorFromNextUrl(result.data.next) };
}

export async function updateMemberRole(
  slug: string,
  membershipId: string,
  body: MembershipRoleUpdateBody,
): Promise<MembershipOut> {
  const result = await generatedUpdateMemberRole(slug, membershipId, body as never);
  return result.data;
}

export async function removeMember(slug: string, membershipId: string): Promise<void> {
  await generatedRemoveMember(slug, membershipId);
}

export async function listInvitations(slug: string): Promise<InvitationOut[]> {
  const result = await generatedListInvitations(slug);
  return result.data.results;
}

export async function createInvitation(
  slug: string,
  body: InvitationCreateBody,
): Promise<InvitationOut> {
  const result = await generatedCreateInvitation(slug, body as never);
  return result.data;
}

export async function revokeInvitation(slug: string, invitationId: string): Promise<void> {
  await generatedRevokeInvitation(slug, invitationId);
}

export async function listRoles(slug: string): Promise<RoleWithPermissions[]> {
  const result = await generatedListRoles(slug);
  return result.data.results as RoleWithPermissions[];
}

export async function getPermissionsRegistry(): Promise<PermissionsRegistryResponse> {
  const result = await generatedPermissionsRegistry();
  return result.data as unknown as PermissionsRegistryResponse;
}

export async function resolveInvitation(token: string): Promise<InviteResolveResponse> {
  const result = await generatedInviteDetail(token);
  return result.data as unknown as InviteResolveResponse;
}

export async function acceptInvitation(token: string): Promise<InviteAcceptResponse> {
  const result = await generatedInviteAccept(token);
  return result.data as unknown as InviteAcceptResponse;
}
