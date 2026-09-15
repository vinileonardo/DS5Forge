import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProfileLoadResponse } from "../../lib/api/contracts";
import { ProfilesPage } from "./ProfilesPage";

const model = vi.hoisted(() => ({ value: {} as unknown }));

vi.mock("../../lib/runtime/RuntimeProvider", () => ({
  useRuntime: () => model.value,
}));

afterEach(cleanup);

function makeValue(loadControllerProfile: (name: string) => Promise<ProfileLoadResponse>) {
  return {
    profiles: [{ name: "Heavy Impacts", source: "bundled", editable: false }],
    config: { rumble: {} },
    runtime: { active_profile: "Default" },
    coreStatus: "online",
    stale: false,
    loadControllerProfile,
    saveControllerProfile: vi.fn(),
    exportProfile: vi.fn(),
    importProfile: vi.fn(),
    deleteProfile: vi.fn(),
  };
}

describe("ProfilesPage apply feedback", () => {
  it("reports unsupported hardware sections instead of only saying applied", async () => {
    const loadControllerProfile = vi.fn().mockResolvedValue({
      profile: "Heavy Impacts",
      config: { rumble: {} },
      unsupported_sections: ["lightbar", "triggers"],
      state: null,
    } as unknown as ProfileLoadResponse);
    model.value = makeValue(loadControllerProfile);

    render(<ProfilesPage />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(loadControllerProfile).toHaveBeenCalledWith("Heavy Impacts"));
    expect(
      await screen.findByText(/The connected runtime does not support: lightbar, triggers/i),
    ).toBeVisible();
    expect(screen.getByText("Profile “Heavy Impacts” applied.")).toBeVisible();
  });

  it("does not show a stale unsupported notice when the profile applies cleanly", async () => {
    const loadControllerProfile = vi.fn().mockResolvedValue({
      profile: "Heavy Impacts",
      config: { rumble: {} },
      unsupported_sections: [],
      state: null,
    } as unknown as ProfileLoadResponse);
    model.value = makeValue(loadControllerProfile);

    render(<ProfilesPage />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(loadControllerProfile).toHaveBeenCalled());
    expect(screen.queryByText(/were not applied/i)).not.toBeInTheDocument();
  });
});
