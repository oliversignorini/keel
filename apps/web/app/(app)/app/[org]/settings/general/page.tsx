"use client";

import { Can } from "@/components/org/can";
import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import {
  deleteOrganization,
  listMembers,
  transferOwnership,
  updateOrganization,
} from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import type { MembershipOut } from "@keel/api-client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  buttonVariants,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@keel/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

interface NameFormValues {
  name: string;
}

/**
 * `/app/[org]/settings/general` (PRD §5 Routes). Name, transfer
 * ownership, and delete — the three General-tab actions PRD §3 lists for
 * an Owner. Every action button is wrapped in `<Can>` (presentation only —
 * see components/org/can.tsx and
 * lib/org/can-is-presentation-only.test.tsx), but the actual mutation
 * always goes through the same API call regardless, so a 403 from the
 * server is still the real gate.
 */
export default function GeneralSettingsPage() {
  const router = useRouter();
  const { currentOrg, refetch } = useOrgContext();
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<NameFormValues>({ values: currentOrg ? { name: currentOrg.name } : undefined });

  if (!currentOrg) return null;

  async function onSubmit(values: NameFormValues) {
    setFormError(null);
    setSaved(false);
    try {
      await updateOrganization(currentOrg!.slug, { name: values.name });
      await refetch();
      setSaved(true);
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Organisation name</CardTitle>
          <CardDescription>
            The name teammates see in the organisation switcher and in invitations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit(onSubmit)}
            noValidate
            className="flex max-w-sm flex-col gap-3"
          >
            {formError ? <p className="text-sm text-destructive">{formError}</p> : null}
            {saved ? <p className="text-sm text-success">Saved.</p> : null}
            <div className="flex flex-col gap-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                aria-invalid={errors.name ? true : undefined}
                disabled={!currentOrg.permissions.includes(Perm.ORG_UPDATE)}
                {...register("name", { required: "Name is required." })}
              />
              {errors.name ? (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              ) : null}
            </div>
            <Can code={Perm.ORG_UPDATE}>
              <Button type="submit" disabled={isSubmitting} className="self-start">
                {isSubmitting ? "Saving…" : "Save"}
              </Button>
            </Can>
          </form>
        </CardContent>
      </Card>

      <Can code={Perm.ORG_TRANSFER}>
        <TransferSection orgSlug={currentOrg.slug} onTransferred={refetch} />
      </Can>

      <Can code={Perm.ORG_DELETE}>
        <DangerZone
          orgName={currentOrg.name}
          onDelete={async () => {
            await deleteOrganization(currentOrg.slug);
            router.push("/");
          }}
        />
      </Can>
    </div>
  );
}

function TransferSection({
  orgSlug,
  onTransferred,
}: {
  orgSlug: string;
  onTransferred: () => Promise<void>;
}) {
  const [members, setMembers] = useState<MembershipOut[]>([]);
  const [targetId, setTargetId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listMembers(orgSlug).then((result) => {
      if (!cancelled) setMembers(result);
    });
    return () => {
      cancelled = true;
    };
  }, [orgSlug]);

  const target = members.find((member) => member.id === targetId);

  async function transfer() {
    if (!targetId) return;
    setSubmitting(true);
    setError(null);
    try {
      await transferOwnership(orgSlug, { membership_id: targetId });
      await onTransferred();
    } catch {
      setError("Could not transfer ownership.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Transfer ownership</CardTitle>
        <CardDescription>
          Hand this organisation to another member. You stay on as an Admin.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? <p className="mb-2 text-sm text-destructive">{error}</p> : null}
        <div className="flex max-w-sm gap-2">
          <Label htmlFor="transfer-target" className="sr-only">
            New owner
          </Label>
          <Select value={targetId} onValueChange={setTargetId}>
            <SelectTrigger id="transfer-target" className="flex-1">
              <SelectValue placeholder="Select a member…" />
            </SelectTrigger>
            <SelectContent>
              {members.map((member) => (
                <SelectItem key={member.id} value={member.id}>
                  {member.user.name || member.user.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" disabled={!targetId || submitting}>
                Transfer
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Transfer ownership?</AlertDialogTitle>
                <AlertDialogDescription>
                  {target ? target.user.name || target.user.email : "This member"} becomes the Owner
                  of this organisation, and you become an Admin.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => void transfer()}>
                  Transfer ownership
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Deleting an organisation is irreversible and was one `window.confirm()`
 * OK-click away (finding 2). The confirm button stays disabled until the
 * organisation's name is typed exactly, which is the standard guard for a
 * destructive action with no undo.
 */
function DangerZone({ orgName, onDelete }: { orgName: string; onDelete: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setTyped("");
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Card className="border-destructive">
      <CardHeader>
        <CardTitle className="text-destructive">Danger zone</CardTitle>
        <CardDescription>
          Deleting an organisation removes all its data. This cannot be undone.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AlertDialog open={open} onOpenChange={onOpenChange}>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">Delete organisation</Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {orgName}?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently removes the organisation and all of its data — members,
                invitations, and everything created inside it. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="flex flex-col gap-2">
              <Label htmlFor="confirm-org-name">
                Type <span className="font-semibold text-foreground">{orgName}</span> to confirm
              </Label>
              <Input
                id="confirm-org-name"
                autoComplete="off"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
              />
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className={buttonVariants({ variant: "destructive" })}
                disabled={typed !== orgName || deleting}
                onClick={(event) => {
                  // Radix closes the dialog on action click; the delete is
                  // async and navigates on success, so let it close and let
                  // the router take over.
                  if (typed !== orgName) {
                    event.preventDefault();
                    return;
                  }
                  void confirmDelete();
                }}
              >
                {deleting ? "Deleting…" : "Delete organisation"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
