import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog, Toggle } from "./ui";

describe("accessible shared controls", () => {
  it("renders a labelled toggle with explicit checked state", () => {
    render(<Toggle label="Haptics" description="Audio rumble" checked onChange={() => undefined} />);
    expect(screen.getByRole("checkbox", { name: "Haptics" })).toBeChecked();
    expect(screen.getByText("Audio rumble")).toBeVisible();
  });

  it("traps dialog focus, closes on Escape and restores the trigger focus", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open delete dialog</button>
          {open && (
            <ConfirmDialog
              title="Delete profile?"
              description="This cannot be undone."
              confirmLabel="Delete profile"
              onConfirm={() => undefined}
              onCancel={() => {
                onCancel();
                setOpen(false);
              }}
            />
          )}
        </>
      );
    }

    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open delete dialog" });
    await user.click(trigger);

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Delete profile" });
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(cancel).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirm).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
