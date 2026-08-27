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

  async function onDelete() {
    if (!window.confirm(`Delete ${currentOrg!.name}? This cannot be undone.`)) return;
    await deleteOrganization(currentOrg!.slug);
    router.push("/");
  }

  return (
    <div className="flex flex-col gap-10">
      <section>
        <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Organisation name
        </h2>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex max-w-sm flex-col gap-3">
          {formError ? <p className="text-sm text-red-600 dark:text-red-400">{formError}</p> : null}
          {saved ? <p className="text-sm text-green-700 dark:text-green-400">Saved.</p> : null}
          <div className="flex flex-col gap-1">
            <label
              htmlFor="name"
              className="text-sm font-medium text-neutral-900 dark:text-neutral-100"
            >
              Name
            </label>
            <input
              id="name"
              className="rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              disabled={!currentOrg.permissions.includes(Perm.ORG_UPDATE)}
              {...register("name", { required: "Name is required." })}
            />
            {errors.name ? (
              <p className="text-sm text-red-600 dark:text-red-400">{errors.name.message}</p>
            ) : null}
          </div>
          <Can code={Perm.ORG_UPDATE}>
            <button
              type="submit"
              disabled={isSubmitting}
              className="self-start rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {isSubmitting ? "Saving…" : "Save"}
            </button>
          </Can>
        </form>
      </section>

      <Can code={Perm.ORG_TRANSFER}>
        <TransferSection orgSlug={currentOrg.slug} onTransferred={refetch} />
      </Can>

      <Can code={Perm.ORG_DELETE}>
        <section className="rounded-lg border border-red-200 p-4 dark:border-red-900">
          <h2 className="mb-1 text-sm font-semibold text-red-700 dark:text-red-400">Danger zone</h2>
          <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
            Deleting an organisation removes all its data. This cannot be undone.
          </p>
          <button
            type="button"
            onClick={() => void onDelete()}
            className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 dark:border-red-800 dark:text-red-400"
          >
            Delete organisation
          </button>
        </section>
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

  async function transfer() {
    if (!targetId) return;
    if (!window.confirm("Transfer ownership? You will become an Admin.")) return;
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
    <section>
      <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Transfer ownership
      </h2>
      {error ? <p className="mb-2 text-sm text-red-600 dark:text-red-400">{error}</p> : null}
      <div className="flex max-w-sm gap-2">
        <select
          value={targetId}
          onChange={(event) => setTargetId(event.target.value)}
          className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
        >
          <option value="">Select a member…</option>
          {members.map((member) => (
            <option key={member.id} value={member.id}>
              {member.user.name || member.user.email}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void transfer()}
          disabled={!targetId || submitting}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-neutral-700"
        >
          Transfer
        </button>
      </div>
    </section>
  );
}
