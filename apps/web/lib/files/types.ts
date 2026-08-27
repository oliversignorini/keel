/**
 * Re-exports of the generated files types (posd#7: the phase-13 fix for
 * this app's own hand-transcribed shadow of the server's shapes —
 * `createUpload` returned a bare `dict` under DRF/phase-10, so orval
 * generated `data: void` and this file existed to paper over that.
 * `keel.files.schemas.PresignedUploadOut` (apps/api/keel/files/schemas.py)
 * fixes the server side; this file now just re-exports the real
 * generated types instead of re-declaring them by hand.
 */

export type {
  FileUploadOut as FileUploadResource,
  FileUploadOutStatus as FileUploadStatus,
  PresignedUploadOut as PresignedUploadResponse,
  PresignedUploadRequest,
} from "@keel/api-client";
