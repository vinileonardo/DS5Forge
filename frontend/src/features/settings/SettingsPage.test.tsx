import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Config } from "../../lib/api/contracts";
import { SettingsPage } from "./SettingsPage";

const model = vi.hoisted(() => ({ value: {} as unknown }));

vi.mock("../../lib/runtime/RuntimeProvider", () => ({
  useRuntime: () => model.value,
}));

afterEach(cleanup);

function makeConfig(): Config {
  return {
    schema_version: 1,
    theme: "Dark",
    mic_button: "master",
    rumble: {
      heavy_cutoff_hz: 180,
      texture_center_hz: 300,
      fast_attack_ms: 5,
      fast_release_ms: 110,
      baseline_attack_ms: 350,
      baseline_release_ms: 1800,
      gate: 0.05,
      impact_level: 0.55,
      gamma: 2.2,
      transient_min_level: 0.22,
      transient_gain: 3,
      transient_weight: 0.6,
      drive_gate: 0.06,
      texture_gate_mult: 1.4,
      min_rumble: 28,
      max_rumble: 255,
    },
    trackpad: {
      trackpad_enabled_on_start: true,
      pointer_speed: 0.75,
      acceleration: 0.006,
      accel_cap: 1.2,
      scroll_speed: 0.35,
      tap_to_click: true,
    },
  } as Config;
}

function makeValue(updateConfig: (patch: unknown) => Promise<Config>) {
  return { config: makeConfig(), coreStatus: "online", updateConfig };
}

describe("SettingsPage recovery surfaces", () => {
  it("keeps desktop recovery and signed updates available while the core is offline", async () => {
    model.value = { config: null, coreStatus: "offline", updateConfig: vi.fn() };
    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeVisible();
    expect(screen.getByText("Core preferences unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: /restart core/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /check for updates/i })).toBeEnabled();
    expect(screen.queryByLabelText("Theme")).not.toBeInTheDocument();
  });
});

describe("SettingsPage draft handling", () => {
  it("preserves an unsaved setting across a config refresh", async () => {
    model.value = makeValue(vi.fn());
    const { rerender } = render(<SettingsPage />);
    const theme = await screen.findByLabelText("Theme");
    fireEvent.change(theme, { target: { value: "Light" } });
    expect(theme).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();

    model.value = { ...makeValue(vi.fn()), config: makeConfig() };
    rerender(<SettingsPage />);

    expect(screen.getByLabelText("Theme")).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();
  });

  it("keeps the setting after a rejected save instead of reverting to persisted values", async () => {
    const updateConfig = vi.fn().mockRejectedValue(new Error("server rejected the patch"));
    model.value = makeValue(updateConfig);
    render(<SettingsPage />);
    const theme = await screen.findByLabelText("Theme");
    fireEvent.change(theme, { target: { value: "Light" } });
    fireEvent.click(screen.getByRole("button", { name: /save settings/i }));

    await waitFor(() => expect(updateConfig).toHaveBeenCalled());
    expect(screen.getByLabelText("Theme")).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();
  });
});
