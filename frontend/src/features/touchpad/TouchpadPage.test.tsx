import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Config, RuntimeState } from "../../lib/api/contracts";
import { TouchpadPage } from "./TouchpadPage";

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
      gestures_enabled: true,
      two_finger_scroll: true,
      swipe_enabled: true,
      swipe_threshold: 40,
    },
  } as Config;
}

const runtime = {
  capabilities: { usb: true, rumble: true, touchpad: true, microphone_button: true },
  touchpad_enabled: true,
  input: undefined,
} as unknown as RuntimeState;

function makeValue(updateConfig: (patch: unknown) => Promise<Config>) {
  return {
    config: makeConfig(),
    runtime,
    coreStatus: "online",
    stale: false,
    canControl: true,
    updateConfig,
    setTouchpad: vi.fn(),
  };
}

describe("TouchpadPage draft handling", () => {
  it("preserves an unsaved draft across a config refresh", async () => {
    model.value = makeValue(vi.fn());
    const { rerender } = render(<TouchpadPage />);
    const pointerSpeed = await screen.findByLabelText("Pointer speed");
    fireEvent.change(pointerSpeed, { target: { value: "1.5" } });
    expect(pointerSpeed).toHaveValue(1.5);
    expect(screen.getByText("Unsaved changes")).toBeVisible();

    model.value = { ...makeValue(vi.fn()), config: makeConfig() };
    rerender(<TouchpadPage />);

    expect(screen.getByLabelText("Pointer speed")).toHaveValue(1.5);
    expect(screen.getByText("Unsaved changes")).toBeVisible();
  });

  it("keeps the draft after a rejected save instead of reverting to persisted values", async () => {
    const updateConfig = vi.fn().mockRejectedValue(new Error("server rejected the patch"));
    model.value = makeValue(updateConfig);
    render(<TouchpadPage />);
    const pointerSpeed = await screen.findByLabelText("Pointer speed");
    fireEvent.change(pointerSpeed, { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: /save touchpad/i }));

    await waitFor(() => expect(updateConfig).toHaveBeenCalled());
    expect(screen.getByLabelText("Pointer speed")).toHaveValue(1.5);
    expect(screen.getByText("Unsaved changes")).toBeVisible();
  });
});
