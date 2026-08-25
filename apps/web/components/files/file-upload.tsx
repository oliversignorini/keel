"use client";

import { useCallback, useRef, useState } from "react";

import {
  completeUpload,
  createPresignedUpload,
  getFileUpload,
  uploadToPresignedUrl,
} from "@/lib/files/api";
import type { FileUploadResource } from "@/lib/files/types";

type UploadPhase = "idle" | "presigning" | "uploading" | "completing" | "done" | "error";

interface FileUploadState {
  phase: UploadPhase;
  progress: number;
  file: FileUploadResource | null;
  error: string | null;
}

const IDLE_STATE: FileUploadState = { phase: "idle", progress: 0, file: null, error: null };

interface FileUploadProps {
  orgSlug: string;
  /** Fires once the row reaches `complete` — the reconciled row, not
   * just the upload's local state, so a caller that stores the file id
   * always has the server's view of it. */
  onComplete?: (file: FileUploadResource) => void;
}

/**
 * `<FileUpload>` (PRD §5 component inventory; docs/plans/phase-5.md 5.6):
 * presign → direct PUT to R2 with progress → complete → reconcile.
 *
 * "Reconciliation" here means the component never trusts its own
 * in-memory belief that an upload finished — the `complete` call
 * returns the `FileUpload` row as the server now sees it (this is also
 * where a browser that already PUT the bytes but never got acknowledged
 * — e.g. after a retry — settles onto the server's actual state rather
 * than the client's guess).
 */
export function FileUpload({ orgSlug, onComplete }: FileUploadProps) {
  const [state, setState] = useState<FileUploadState>(IDLE_STATE);
  const pendingFileRef = useRef<File | null>(null);

  const runUpload = useCallback(
    async (selected: File) => {
      pendingFileRef.current = selected;
      setState({ phase: "presigning", progress: 0, file: null, error: null });
      try {
        const { file, upload_url: uploadUrl } = await createPresignedUpload(orgSlug, {
          filename: selected.name,
          content_type: selected.type || "application/octet-stream",
          size: selected.size,
        });

        setState({ phase: "uploading", progress: 0, file, error: null });
        await uploadToPresignedUrl(uploadUrl, selected, (fraction) => {
          setState((previous) => ({ ...previous, progress: fraction }));
        });

        setState((previous) => ({ ...previous, phase: "completing" }));
        const completed = await completeUpload(orgSlug, file.id);

        setState({ phase: "done", progress: 1, file: completed, error: null });
        onComplete?.(completed);
      } catch (error) {
        setState((previous) => ({
          ...previous,
          phase: "error",
          error: error instanceof Error ? error.message : "Upload failed.",
        }));
      }
    },
    [orgSlug, onComplete],
  );

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const selected = event.target.files?.[0];
      event.target.value = ""; // lets picking the same file twice re-fire onChange
      if (selected) {
        void runUpload(selected);
      }
    },
    [runUpload],
  );

  const handleRetry = useCallback(() => {
    if (pendingFileRef.current) {
      void runUpload(pendingFileRef.current);
    }
  }, [runUpload]);

  /** Reconciliation on demand: re-fetches the row from the server rather
   * than trusting local state — for a caller that suspects its view is
   * stale (e.g. after remounting mid-upload). */
  const handleReconcile = useCallback(async () => {
    if (!state.file) return;
    const reconciled = await getFileUpload(orgSlug, state.file.id);
    setState((previous) => ({ ...previous, file: reconciled }));
    if (reconciled.status === "complete") {
      onComplete?.(reconciled);
    }
  }, [orgSlug, state.file, onComplete]);

  return (
    <div data-testid="file-upload">
      <input
        type="file"
        aria-label="Upload file"
        onChange={handleFileChange}
        disabled={
          state.phase === "presigning" ||
          state.phase === "uploading" ||
          state.phase === "completing"
        }
      />

      {state.phase === "uploading" && (
        <div
          role="progressbar"
          aria-valuenow={Math.round(state.progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          Uploading… {Math.round(state.progress * 100)}%
        </div>
      )}

      {state.phase === "completing" && <div>Finishing…</div>}

      {state.phase === "done" && state.file && <div>Uploaded: {state.file.key}</div>}

      {state.phase === "error" && (
        <div role="alert">
          <span>{state.error}</span>
          <button type="button" onClick={handleRetry}>
            Retry
          </button>
        </div>
      )}

      {state.file && state.file.status === "pending" && (
        <button type="button" onClick={() => void handleReconcile()}>
          Check status
        </button>
      )}
    </div>
  );
}
