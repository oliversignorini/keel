/**
 * Thin, typed wrappers around the generated files client — the same
 * shape, and for the same reasons, as lib/billing/api.ts. Uses the
 * generated request/response types directly now (posd#7) rather than
 * casting through a hand-written shadow of them.
 */

import {
  unwrapData,
  completeUpload as generatedCompleteUpload,
  createUpload,
  retrieveUpload,
} from "@keel/api-client";

import type { FileUploadResource, PresignedUploadResponse } from "./types";

/** SHA-256 of `file`'s bytes, hex-encoded — the server verifies this
 * against what actually lands in storage before an upload can reach
 * `available` (apps/api/keel/files/services.py's `complete_upload`;
 * docs/plans/phase-13.md, ddia#21). Computed client-side via
 * `SubtleCrypto` so the declaration travels with the create-upload
 * request rather than needing a second round trip. */
async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/** Requires `files.manage`. Returns the created `FileUpload` row (status
 * `pending`) plus the presigned URL to PUT the bytes straight to
 * storage. */
export async function createPresignedUpload(
  orgSlug: string,
  file: File,
): Promise<PresignedUploadResponse> {
  const result = await createUpload(orgSlug, {
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    size: file.size,
    checksum_sha256: await sha256Hex(file),
  });
  return unwrapData(result);
}

/** The browser's direct upload to storage — never proxied through
 * Django (PRD §5, "the browser uploads straight to storage"). Reports
 * progress via `XMLHttpRequest` (unlike `fetch`, it exposes upload
 * progress events), which is why this isn't just a
 * `fetch(uploadUrl, { method: "PUT" })`. */
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

/** Requires `files.manage`. Confirms the object landed in storage and
 * moves the row to `available` (apps/api/keel/files/services.py verifies
 * the checksum and the object's actual existence before doing so). */
export async function completeUpload(orgSlug: string, fileId: string): Promise<FileUploadResource> {
  const result = await generatedCompleteUpload(orgSlug, fileId, { method: "POST" });
  return unwrapData(result);
}

/** Requires `files.view`. Used to reconcile a `FileUpload` row's status
 * after a page reload — see `<FileUpload>`'s docstring. */
export async function getFileUpload(orgSlug: string, fileId: string): Promise<FileUploadResource> {
  const result = await retrieveUpload(orgSlug, fileId);
  return unwrapData(result);
}
