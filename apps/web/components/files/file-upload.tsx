"use client";

import { useCallback, useRef, useState } from "react";

import {
  completeUpload,
  createPresignedUpload,
  getFileUpload,
  uploadToPresignedUrl,
} from "@/lib/files/api";
import type { FileUploadResource } from "@/lib/files/types";
import { Alert, AlertDescription, Button, Progress } from "@keel/ui";
import { CheckCircle2, FileIcon, Loader2, RefreshCw, Upload } from "lucide-react";

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
  /** Fires once the row reaches `available` — the reconciled row, not
   * just the upload's local state, so a caller that stores the file id
   * always has the server's view of it. */
  onComplete?: (file: FileUploadResource) => void;
}

/**
 * `<FileUpload>`: presign → direct PUT to storage with progress →
 * complete → reconcile.
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

  const busy =
    state.phase === "presigning" || state.phase === "uploading" || state.phase === "completing";

  const runUpload = useCallback(
    async (selected: File) => {
      pendingFileRef.current = selected;
      setState({ phase: "presigning", progress: 0, file: null, error: null });
      try {
        const { file, upload_url: uploadUrl } = await createPresignedUpload(orgSlug, selected);

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
    if (reconciled.status === "available") {
      onComplete?.(reconciled);
    }
  }, [orgSlug, state.file, onComplete]);

  return (
    <div data-testid="file-upload" className="flex flex-col gap-3">
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed border-input px-6 py-8 text-center text-sm text-muted-foreground hover:bg-accent/50 has-[:disabled]:pointer-events-none has-[:disabled]:opacity-50">
        {busy ? <Loader2 className="size-6 animate-spin" /> : <Upload className="size-6" />}
        <span>{busy ? "Uploading…" : "Click to choose a file, or drag one here"}</span>
        <input
          type="file"
          aria-label="Upload file"
          className="sr-only"
          onChange={handleFileChange}
          disabled={busy}
        />
      </label>

      {state.phase === "uploading" && (
        <div className="flex flex-col gap-1">
          <Progress value={Math.round(state.progress * 100)} />
          <span className="text-xs text-muted-foreground">
            Uploading… {Math.round(state.progress * 100)}%
          </span>
        </div>
      )}

      {state.phase === "completing" && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Finishing…
        </p>
      )}

      {state.phase === "done" && state.file && (
        <p className="flex items-center gap-2 text-sm text-foreground">
          <CheckCircle2 className="size-4 text-success" />
          Uploaded: {state.file.filename}
        </p>
      )}

      {state.phase === "error" && (
        <Alert variant="destructive">
          <AlertDescription className="flex items-center justify-between gap-3">
            <span>{state.error}</span>
            <Button type="button" variant="outline" size="sm" onClick={handleRetry}>
              <RefreshCw />
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {state.file && state.file.status === "pending" && (
        <Button type="button" variant="outline" size="sm" onClick={() => void handleReconcile()}>
          <FileIcon />
          Check status
        </Button>
      )}
    </div>
  );
}
