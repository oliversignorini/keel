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
import { ApiError, type InvitationOut, type MembershipOut } from "@keel/api-client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Avatar,
  AvatarFallback,
  Badge,
  Button,
  buttonVariants,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@keel/ui";
import { MoreHorizontal, Trash2 } from "lucide-react";
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
  const [members, setMembers] = useState<MembershipOut[]>([]);
  const [invitations, setInvitations] = useState<InvitationOut[]>([]);
  const [roles, setRoles] = useState<RoleWithPermissions[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  // The remove dialog lives outside the row's `<DropdownMenu>` on purpose:
  // the menu unmounts its content when it closes, which would tear the
  // dialog down with it mid-open.
  const [pendingRemoval, setPendingRemoval] = useState<MembershipOut | null>(null);

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

  const pending = invitations.filter((invitation) => invitation.status === "pending");

  return (
    <div className="flex flex-col gap-6">
      {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>Everyone with access to this organisation.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <MembersSkeleton />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Member</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="w-0" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((member) => {
                  const displayName = member.user.name || member.user.email;
                  return (
                    <TableRow key={member.id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar>
                            <AvatarFallback>{initials(displayName)}</AvatarFallback>
                          </Avatar>
                          <div className="flex flex-col">
                            <span className="font-medium text-foreground">{displayName}</span>
                            {member.user.name ? (
                              <span className="text-xs text-muted-foreground">
                                {member.user.email}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Can
                          code={Perm.MEMBERS_CHANGE_ROLE}
                          fallback={<Badge variant="secondary">{member.role.name}</Badge>}
                        >
                          <Select
                            value={member.role.id}
                            onValueChange={(roleId) => void handleRoleChange(member.id, roleId)}
                          >
                            {/* The native selects this replaced had no
                                accessible name at all — axe `select-name`,
                                critical, one node per row (finding 4). */}
                            <SelectTrigger className="w-36" aria-label={`Role for ${displayName}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {roles.map((role) => (
                                <SelectItem key={role.id} value={role.id}>
                                  {role.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </Can>
                      </TableCell>
                      <TableCell className="text-right">
                        <Can code={Perm.MEMBERS_REMOVE}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={`Actions for ${displayName}`}
                              >
                                <MoreHorizontal />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                variant="destructive"
                                onSelect={() => setPendingRemoval(member)}
                              >
                                <Trash2 />
                                Remove member
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </Can>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRemoval(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this member?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval
                ? `${pendingRemoval.user.name || pendingRemoval.user.email} loses access to this organisation immediately. They can be invited back later.`
                : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={() => {
                if (pendingRemoval) void handleRemove(pendingRemoval.id);
              }}
            >
              Remove member
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Card>
        <CardHeader>
          <CardTitle>Pending invitations</CardTitle>
          <CardDescription>Invitations that haven&apos;t been accepted yet.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-10 w-full" />
          ) : pending.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending invitations.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="w-0" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pending.map((invitation) => (
                  <TableRow key={invitation.id}>
                    <TableCell className="text-foreground">{invitation.email}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{invitation.role.name}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Can code={Perm.MEMBERS_INVITE}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleRevoke(invitation.id)}
                        >
                          Revoke
                        </Button>
                      </Can>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Can code={Perm.MEMBERS_INVITE}>
        <InviteForm orgSlug={currentOrg.slug} roles={roles} onInvited={load} />
      </Can>
    </div>
  );
}

/** Up to two initials from a display name, falling back to the first
 * character of an email local part. */
function initials(displayName: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0]![0]! + words[1]![0]!).toUpperCase();
  }
  return displayName.slice(0, 2).toUpperCase();
}

function MembersSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Loading members">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-8 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-8 w-36" />
        </div>
      ))}
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
    <Card>
      <CardHeader>
        <CardTitle>Invite a member</CardTitle>
        <CardDescription>
          They&apos;ll get an email with a link to join this organisation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex max-w-md flex-col gap-3">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              required
              placeholder="teammate@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-role">Role</Label>
            <Select value={roleId} onValueChange={setRoleId}>
              <SelectTrigger id="invite-role">
                <SelectValue placeholder="Select a role…" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.id}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={submitting} className="self-start">
            {submitting ? "Sending…" : "Send invitation"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
