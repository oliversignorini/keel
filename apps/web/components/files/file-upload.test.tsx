import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileUpload } from "./file-upload";

const createPresignedUploadMock = vi.fn();
const uploadToPresignedUrlMock = vi.fn();
const completeUploadMock = vi.fn();
const getFileUploadMock = vi.fn();

vi.mock("@/lib/files/api", () => ({
  createPresignedUpload: (...args: unknown[]) => createPresignedUploadMock(...args),
  uploadToPresignedUrl: (...args: unknown[]) => uploadToPresignedUrlMock(...args),
  completeUpload: (...args: unknown[]) => completeUploadMock(...args),
  getFileUpload: (...args: unknown[]) => getFileUploadMock(...args),
}));

const PENDING_FILE = {
  id: "file-1",
  key: "org/1/uuid/report.pdf",
  content_type: "application/pdf",
  size: 100,
  status: "pending",
  created_at: "2026-01-01T00:00:00Z",
};

const COMPLETE_FILE = { ...PENDING_FILE, status: "complete" as const };

function selectFile() {
  const input = screen.getByLabelText("Upload file") as HTMLInputElement;
  const file = new File(["hello"], "report.pdf", { type: "application/pdf" });
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  createPresignedUploadMock.mockReset();
  uploadToPresignedUrlMock.mockReset();
  completeUploadMock.mockReset();
  getFileUploadMock.mockReset();
});

describe("<FileUpload>", () => {
  it("presigns, uploads with progress, completes, and reports the reconciled row", async () => {
    createPresignedUploadMock.mockResolvedValue({
      file: PENDING_FILE,
      upload_url: "https://r2.example.com/presigned",
    });
    uploadToPresignedUrlMock.mockImplementation(
      async (_url: string, _file: File, onProgress?: (fraction: number) => void) => {
        onProgress?.(0.5);
        onProgress?.(1);
      },
    );
    completeUploadMock.mockResolvedValue(COMPLETE_FILE);
    const onComplete = vi.fn();

    render(<FileUpload orgSlug="acme" onComplete={onComplete} />);
    selectFile();

    await screen.findByText(/Uploaded: org\/1\/uuid\/report\.pdf/);

    expect(createPresignedUploadMock).toHaveBeenCalledWith("acme", {
      filename: "report.pdf",
      content_type: "application/pdf",
      size: 5,
    });
    expect(completeUploadMock).toHaveBeenCalledWith("acme", "file-1");
    expect(onComplete).toHaveBeenCalledWith(COMPLETE_FILE);
  });

  it("shows a retry control when the upload fails, and retrying re-runs the same flow", async () => {
    createPresignedUploadMock.mockResolvedValue({
      file: PENDING_FILE,
      upload_url: "https://r2.example.com/presigned",
    });
    uploadToPresignedUrlMock
      .mockRejectedValueOnce(new Error("network blip"))
      .mockResolvedValueOnce(undefined);
    completeUploadMock.mockResolvedValue(COMPLETE_FILE);

    render(<FileUpload orgSlug="acme" />);
    selectFile();

    await screen.findByRole("alert");
    expect(screen.getByText("network blip")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await screen.findByText(/Uploaded:/);
    expect(createPresignedUploadMock).toHaveBeenCalledTimes(2);
  });

  it("reconciles a pending row against the server on demand", async () => {
    createPresignedUploadMock.mockResolvedValue({
      file: PENDING_FILE,
      upload_url: "https://r2.example.com/presigned",
    });
    uploadToPresignedUrlMock.mockResolvedValue(undefined);
    // The complete call itself fails (e.g. a dropped connection after
    // the PUT actually landed) — the row is still checkable by hand.
    completeUploadMock.mockRejectedValue(new Error("timed out"));
    getFileUploadMock.mockResolvedValue(COMPLETE_FILE);
    const onComplete = vi.fn();

    render(<FileUpload orgSlug="acme" onComplete={onComplete} />);
    selectFile();

    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(COMPLETE_FILE));
    expect(getFileUploadMock).toHaveBeenCalledWith("acme", "file-1");
  });
});
