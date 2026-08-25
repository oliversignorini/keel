import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Can } from "./can";

const useOrgContextMock = vi.fn();

vi.mock("@/lib/org/org-context", () => ({
  useOrgContext: () => useOrgContextMock(),
}));

describe("<Can>", () => {
  it("renders children when the current organisation holds the code", () => {
    useOrgContextMock.mockReturnValue({
      currentOrg: { permissions: ["members.invite"] },
    });

    render(
      <Can code="members.invite">
        <button>Invite</button>
      </Can>,
    );

    expect(screen.getByRole("button", { name: "Invite" })).toBeInTheDocument();
  });

  it("renders nothing when the current organisation lacks the code", () => {
    useOrgContextMock.mockReturnValue({
      currentOrg: { permissions: [] },
    });

    render(
      <Can code="members.invite">
        <button>Invite</button>
      </Can>,
    );

    expect(screen.queryByRole("button", { name: "Invite" })).not.toBeInTheDocument();
  });

  it("renders the fallback when provided and the code is absent", () => {
    useOrgContextMock.mockReturnValue({
      currentOrg: { permissions: [] },
    });

    render(<Can code="members.invite" fallback={<span>Member</span>} />);

    expect(screen.getByText("Member")).toBeInTheDocument();
  });

  it("renders nothing while there is no current organisation yet", () => {
    useOrgContextMock.mockReturnValue({ currentOrg: null });

    render(
      <Can code="members.invite">
        <button>Invite</button>
      </Can>,
    );

    expect(screen.queryByRole("button", { name: "Invite" })).not.toBeInTheDocument();
  });
});
