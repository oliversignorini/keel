"use client";

import { Can } from "@/components/org/can";
import {
  createInvitation,
  listInvitations,
  listMembers,
  listRoles,
  removeMember,
  revokeInvitation,
  updateMemberRole,
} from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import type { RoleWithPermissions } from "@/lib/org/types";
import { ApiError, type Invitation, type Membership } from "@keel/api-client";
import { useCallback, useEffect, useState } from "react";

/**
 * `/app/[org]/settings/members` (PRD §5 Routes). Members list with role
 * change and remove, plus pending invitations with revoke and a form to
 * send new ones — the Members-tab actions PRD §3 lists.
 *
 * Every mutation button is wrapped in `<Can>`, which only ever decides
 * what renders (components/org/can.tsx). The actual mutation call below
 * each one is unconditional — if a caller reaches it by any means other
 * than the rendered button (e.g. calling the underlying fetch function
 * directly, bypassing `<Can>` entirely, the way
 * lib/org/can-is-presentation-only.test.tsx does), the server still
 * enforces `required_permissions` and returns 403, because nothing here
 * short-circuits before the request.
 */
export default function MembersSettingsPage() {
  const { currentOrg } = useOrgContext();
  const [members, setMembers] = useState<Membership[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [roles, setRoles] = useState<RoleWithPermissions[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!currentOrg) return;
    setLoading(true);
    const [membersResult, invitationsResult, rolesResult] = await Promise.all([
      listMembers(currentOrg.slug),
      listInvitations(currentOrg.slug),
      listRoles(currentOrg.slug),
    ]);
    setMembers(membersResult);
    setInvitations(invitationsResult);
    setRoles(rolesResult);
    setLoading(false);
  }, [currentOrg]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!currentOrg) return null;

  async function handleRoleChange(membershipId: string, roleId: string) {
    setActionError(null);
    try {
      await updateMemberRole(currentOrg!.slug, membershipId, { role_id: roleId });
      await load();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Could not change role.");
    }
  }

  async function handleRemove(membershipId: string) {
    if (!window.confirm("Remove this member?")) return;
    setActionError(null);
    try {
      await removeMember(currentOrg!.slug, membershipId);
      await load();
    } catch (error) {
      // The last-Owner guard (organizations/permissions.py
      // is_last_active_owner) denies this with reason
      // "cannot_remove_last_owner" — surfaced here via the same
      // ApiError.message every other denial uses.
      setActionError(error instanceof ApiError ? error.message : "Could not remove member.");
    }
  }

  async function handleRevoke(invitationId: string) {
    setActionError(null);
    try {
      await revokeInvitation(currentOrg!.slug, invitationId);
      await load();
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : "Could not revoke invitation.");
    }
  }

  return (
    <div className="flex flex-col gap-10">
      {actionError ? <p className="text-sm text-red-600 dark:text-red-400">{actionError}</p> : null}

      <section>
        <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Members
        </h2>
        {loading ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">Loading…</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                <th className="py-2 font-medium">Member</th>
                <th className="py-2 font-medium">Role</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="py-2 text-neutral-900 dark:text-neutral-100">
                    {member.user.name || member.user.email}
                  </td>
                  <td className="py-2">
                    <Can code={Perm.MEMBERS_CHANGE_ROLE} fallback={member.role.name}>
                      <select
                        value={member.role.id}
                        onChange={(event) => void handleRoleChange(member.id, event.target.value)}
                        className="rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
                      >
                        {roles.map((role) => (
                          <option key={role.id} value={role.id}>
                            {role.name}
                          </option>
                        ))}
                      </select>
                    </Can>
                  </td>
                  <td className="py-2 text-right">
                    <Can code={Perm.MEMBERS_REMOVE}>
                      <button
                        type="button"
                        onClick={() => void handleRemove(member.id)}
                        className="text-red-600 underline dark:text-red-400"
                      >
                        Remove
                      </button>
                    </Can>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Pending invitations
        </h2>
        {invitations.filter((invitation) => invitation.status === "pending").length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-500">No pending invitations.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {invitations
              .filter((invitation) => invitation.status === "pending")
              .map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex items-center justify-between rounded-md border border-neutral-200 px-3 py-2 text-sm dark:border-neutral-800"
                >
                  <span className="text-neutral-900 dark:text-neutral-100">
                    {invitation.email} — {invitation.role.name}
                  </span>
                  <Can code={Perm.MEMBERS_INVITE}>
                    <button
                      type="button"
                      onClick={() => void handleRevoke(invitation.id)}
                      className="text-red-600 underline dark:text-red-400"
                    >
                      Revoke
                    </button>
                  </Can>
                </li>
              ))}
          </ul>
        )}
      </section>

      <Can code={Perm.MEMBERS_INVITE}>
        <InviteForm orgSlug={currentOrg.slug} roles={roles} onInvited={load} />
      </Can>
    </div>
  );
}

function InviteForm({
  orgSlug,
  roles,
  onInvited,
}: {
  orgSlug: string;
  roles: RoleWithPermissions[];
  onInvited: () => Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!roleId) {
      setError("Choose a role.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createInvitation(orgSlug, { email, role_id: roleId });
      setEmail("");
      setRoleId("");
      await onInvited();
    } catch (invitationError) {
      setError(
        invitationError instanceof ApiError
          ? invitationError.message
          : "Could not send invitation.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Invite a member
      </h2>
      <form onSubmit={submit} className="flex max-w-md flex-col gap-3">
        {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
        <input
          type="email"
          required
          placeholder="teammate@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
        />
        <select
          value={roleId}
          onChange={(event) => setRoleId(event.target.value)}
          className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
        >
          <option value="">Select a role…</option>
          {roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={submitting}
          className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {submitting ? "Sending…" : "Send invitation"}
        </button>
      </form>
    </section>
  );
}
