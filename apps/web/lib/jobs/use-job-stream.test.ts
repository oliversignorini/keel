import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useJobStream } from "./use-job-stream";

const listJobsMock = vi.fn();
const getJobMock = vi.fn();

vi.mock("./api", () => ({
  listJobs: (...args: unknown[]) => listJobsMock(...args),
  getJob: (...args: unknown[]) => getJobMock(...args),
  jobStreamUrl: (orgSlug: string) => `https://stream.example.com/${orgSlug}/jobs/stream/`,
}));

type Listener = (event: MessageEvent<string>) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  withCredentials: boolean;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string, options?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = Boolean(options?.withCredentials);
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    (this.listeners[type] ??= []).push(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const payload = { data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.listeners[type] ?? []) listener(payload);
  }
}

function latestSource(): MockEventSource {
  const source = MockEventSource.instances.at(-1);
  if (!source) throw new Error("no EventSource constructed yet");
  return source;
}

const JOB = {
  id: "job-1",
  type: "demo.count_items",
  status: "queued",
  params: {},
  result_ref: "",
  error: "",
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  finished_at: null,
  steps: [],
};

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  listJobsMock.mockReset().mockResolvedValue([JOB]);
  getJobMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useJobStream", () => {
  it("reconciles from the REST list on mount, then connects", async () => {
    const { result } = renderHook(() => useJobStream("acme"));

    await waitFor(() => expect(result.current.jobs).toEqual([JOB]));
    expect(listJobsMock).toHaveBeenCalledWith("acme");
    expect(latestSource().url).toBe("https://stream.example.com/acme/jobs/stream/");
    expect(latestSource().withCredentials).toBe(true);
  });

  it("goes live on open and applies a job event", async () => {
    const { result } = renderHook(() => useJobStream("acme"));
    await waitFor(() => expect(result.current.jobs).toHaveLength(1));

    act(() => latestSource().onopen?.());
    expect(result.current.connection).toBe("live");

    act(() =>
      latestSource().emit("job", {
        type: "job",
        job_id: "job-1",
        status: "running",
        job_type: "demo.count_items",
        result_ref: "",
        error: "",
      }),
    );

    await waitFor(() => expect(result.current.jobs[0]?.status).toBe("running"));
  });

  it("applies a step event onto the matching job", async () => {
    const { result } = renderHook(() => useJobStream("acme"));
    await waitFor(() => expect(result.current.jobs).toHaveLength(1));

    act(() =>
      latestSource().emit("job", {
        type: "step",
        job_id: "job-1",
        step_id: "step-1",
        name: "prepare",
        ordinal: 0,
        status: "succeeded",
        output_ref: "prepared",
        error: "",
      }),
    );

    await waitFor(() => expect(result.current.jobs[0]?.steps).toHaveLength(1));
    expect(result.current.jobs[0]?.steps[0]).toMatchObject({
      id: "step-1",
      name: "prepare",
      status: "succeeded",
    });
  });

  it("falls back to polling on error and stops polling once reconnected", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    getJobMock.mockResolvedValue({ ...JOB, status: "running" });

    const { result } = renderHook(() => useJobStream("acme"));
    await waitFor(() => expect(result.current.jobs).toHaveLength(1));

    act(() => latestSource().onerror?.());
    expect(result.current.connection).toBe("polling");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });
    expect(getJobMock).toHaveBeenCalledWith("acme", "job-1");

    act(() => latestSource().onopen?.());
    expect(result.current.connection).toBe("live");

    const callsAtReconnect = getJobMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8_000);
    });
    expect(getJobMock.mock.calls.length).toBe(callsAtReconnect);
  });

  it("closes the connection on unmount", async () => {
    const { unmount } = renderHook(() => useJobStream("acme"));
    await waitFor(() => expect(latestSource()).toBeDefined());

    const source = latestSource();
    unmount();

    expect(source.closed).toBe(true);
  });
});
