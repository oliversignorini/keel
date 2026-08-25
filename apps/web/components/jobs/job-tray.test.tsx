import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JobTray } from "./job-tray";

const useJobStreamMock = vi.fn();

vi.mock("@/lib/jobs/use-job-stream", () => ({
  useJobStream: (...args: unknown[]) => useJobStreamMock(...args),
}));

const RUNNING_JOB = {
  id: "job-1",
  type: "demo.count_items",
  status: "running",
  params: {},
  result_ref: "",
  error: "",
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:01Z",
  finished_at: null,
  steps: [
    {
      id: "step-1",
      name: "prepare",
      ordinal: 0,
      status: "succeeded",
      output_ref: "prepared",
      started_at: null,
      finished_at: null,
      error: "",
    },
  ],
};

describe("<JobTray>", () => {
  it("renders nothing when there are no jobs", () => {
    useJobStreamMock.mockReturnValue({ jobs: [], connection: "live" });

    const { container } = render(<JobTray orgSlug="acme" />);

    expect(container).toBeEmptyDOMElement();
  });

  it("lists jobs with their status and steps", () => {
    useJobStreamMock.mockReturnValue({ jobs: [RUNNING_JOB], connection: "live" });

    render(<JobTray orgSlug="acme" />);

    expect(screen.getByTestId("job-tray-item-job-1")).toBeInTheDocument();
    expect(screen.getByTestId("job-tray-status-job-1")).toHaveTextContent("Running");
    expect(screen.getByTestId("job-tray-step-step-1")).toHaveTextContent("prepare: Succeeded");
    expect(useJobStreamMock).toHaveBeenCalledWith("acme");
  });

  it("shows a polling notice when the stream has fallen back", () => {
    useJobStreamMock.mockReturnValue({ jobs: [RUNNING_JOB], connection: "polling" });

    render(<JobTray orgSlug="acme" />);

    expect(screen.getByTestId("job-tray-polling-notice")).toBeInTheDocument();
  });

  it("surfaces a failed job's error", () => {
    useJobStreamMock.mockReturnValue({
      jobs: [{ ...RUNNING_JOB, status: "failed", error: "boom" }],
      connection: "live",
    });

    render(<JobTray orgSlug="acme" />);

    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });
});
