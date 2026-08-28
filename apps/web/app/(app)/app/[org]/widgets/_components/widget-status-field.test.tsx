import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

import { WidgetStatusField } from "./widget-status-field";

function Harness({ status }: { status?: string }) {
  const { control } = useForm<{ name: string; description?: string; status?: string }>({
    values: { name: "x", status },
  });
  return <WidgetStatusField control={control} />;
}

describe("WidgetStatusField", () => {
  it("shows the human label for a value set asynchronously (edit form load)", async () => {
    render(<Harness status="active" />);
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Select a status")).not.toBeInTheDocument();
  });

  it("shows the placeholder when no status is set (create form)", () => {
    render(<Harness status={undefined} />);
    expect(screen.getByText("Select a status")).toBeInTheDocument();
  });
});
