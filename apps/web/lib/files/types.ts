/**
 * Hand-written types for the files API surface (PRD §5;
 * docs/plans/phase-5.md 5.6), for the same reason lib/billing/types.ts
 * exists — see that file's docstring. ``FileUploadCreateView`` /
 * ``FileUploadDetailView`` / ``FileUploadCompleteView``
 * (apps/api/keel/files/views.py) are plain ``APIView``s with no
 * ``serializer_class``, so orval generates ``data: void`` for all
 * three. Transcribed from apps/api/keel/files/serializers.py.
 */

export type FileUploadStatus = "pending" | "complete";

/** ``FileUploadSerializer``. */
export interface FileUploadResource {
  id: string;
  key: string;
  content_type: string;
  size: number;
  status: FileUploadStatus;
  created_at: string;
}

/** ``POST /organizations/<org_slug>/files/`` response. */
export interface PresignedUploadResponse {
  file: FileUploadResource;
  upload_url: string;
}

/** ``POST /organizations/<org_slug>/files/`` request body
 * (``PresignedUploadRequestSerializer``). */
export interface PresignedUploadRequest {
  filename: string;
  content_type: string;
  size: number;
}
