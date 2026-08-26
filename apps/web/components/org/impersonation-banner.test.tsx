import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const useMeMock = vi.fn();
const impersonationExitCreateMock = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/org/use-me", () => ({
  useMe: () => useMeMock(),
}));

vi.mock("@keel/api-client", () => ({
  impersonationExitCreate: () => impersonationExitCreateMock(),
}));

import { ImpersonationBannerHost } from "./impersonation-banner";

describe("<ImpersonationBannerHost>", () => {
  it("renders nothing for an ordinary session", () => {
    useMeMock.mockReturnValue({
      me: {
        user: { id: "1", email: "a@example.com", name: "A" },
        organizations: [],
        impersonator: null,
      },
    });

    render(<ImpersonationBannerHost />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders the banner with no dismiss control while impersonating", () => {
    useMeMock.mockReturnValue({
      me: {
        user: { id: "1", email: "target@example.com", name: "Target" },
        organizations: [],
        impersonator: { id: "2", email: "staff@example.com", name: "Staff" },
      },
    });

    render(<ImpersonationBannerHost />);

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("staff@example.com");
    expect(banner).toHaveTextContent("target@example.com");
    // Only the exit action — never a close/dismiss button of any kind.
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /exit impersonation/i })).toBeInTheDocument();
  });
});
