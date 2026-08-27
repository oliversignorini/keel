/**
 * Thin, typed wrappers around the generated files client — the same
 * shape, and for the same reasons, as lib/billing/api.ts.
 */

import {
  completeUpload as generatedCompleteUpload,
  createUpload,
  retrieveUpload,
} from "@keel/api-client";

import type { FileUploadResource, PresignedUploadRequest, PresignedUploadResponse } from "./types";

/** Requires `files.manage`. Returns the created `FileUpload` row (status
 * `pending`) plus the presigned URL to PUT the bytes straight to R2. */
export async function createPresignedUpload(
  orgSlug: string,
  body: PresignedUploadRequest,
): Promise<PresignedUploadResponse> {
  const result = await createUpload(orgSlug, body as never);
  return result.data as unknown as PresignedUploadResponse;
}

/** The browser's direct upload to R2 — never proxied through Django
 * (PRD §5, "the browser uploads straight to R2"). Reports progress via
 * `XMLHttpRequest` (unlike `fetch`, it exposes upload progress events),
 * which is why this isn't just a `fetch(uploadUrl, { method: "PUT" })`. */
export function uploadToPresignedUrl(
  uploadUrl: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(event.loaded / event.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed with status ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.send(file);
  });
}

/** Requires `files.manage`. Confirms the object landed in R2 and moves
 * the row to `complete` (apps/api/keel/files/services.py verifies the
 * object actually exists before doing so). */
export async function completeUpload(orgSlug: string, fileId: string): Promise<FileUploadResource> {
  const result = await generatedCompleteUpload(orgSlug, fileId, { method: "POST" });
  return result.data as unknown as FileUploadResource;
}

/** Requires `files.view`. Used to reconcile a `FileUpload` row's status
 * after a page reload — see `<FileUpload>`'s docstring. */
export async function getFileUpload(orgSlug: string, fileId: string): Promise<FileUploadResource> {
  const result = await retrieveUpload(orgSlug, fileId);
  return result.data as unknown as FileUploadResource;
}
