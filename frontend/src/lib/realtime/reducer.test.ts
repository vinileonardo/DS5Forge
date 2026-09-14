import { describe, expect, it } from "vitest";

import type { RuntimeState } from "../api/contracts";
import { applyRuntimeEvent, sessionEventFor } from "./reducer";

const runtime = {
  connection: "disconnected" as const,
  identity: null,
  capabilities: {
    usb: true,
    rumble: true,
    touchpad: true,
    microphone_button: true,
    lightbar: true,
    adaptive_triggers: false,
  },
  battery: { level: 0, charging: null },
  motors: { left: 0, right: 0 },
  rumble_enabled: true,
  touchpad_enabled: true,
  active_profile: "Default",
  config_version: 1,
  audio: { status: "stopped", device: null, error: null },
  last_error: null,
  health: {
    process_alive: true,
    controller_available: false,
    subsystems: { controller: "waiting" },
    degraded: [],
  },
  sequence: 1,
  updated_at: 1,
} satisfies RuntimeState;

describe("realtime projection", () => {
  it("treats the snapshot and state updates as authoritative", () => {
    const next = applyRuntimeEvent(
      { runtime: null, config: null },
      { type: "state.snapshot", version: 1, payload: { state: runtime } },
    );
    expect(next.runtime).toBe(runtime);
    const updated = { ...runtime, sequence: 2, connection: "connected" as const };
    expect(
      applyRuntimeEvent(next, { type: "state.updated", version: 1, payload: { state: updated } }).runtime,
    ).toBe(updated);
  });

  it("marks audio degradation from a validated event", () => {
    const next = applyRuntimeEvent(
      { runtime, config: null },
      {
        type: "audio.status",
        version: 1,
        payload: { status: "error", device: "Speakers", error: "capture failed" },
      },
    );
    expect(next.runtime?.audio.status).toBe("error");
    expect(next.runtime?.health.degraded).toContain("audio");
  });

  it("creates bounded diagnostic timeline entries without changing hardware state", () => {
    const event = {
      type: "diagnostic" as const,
      version: 1 as const,
      payload: { error: { message: "recoverable" } },
    };
    expect(sessionEventFor(event, 4)).toMatchObject({ id: 4, kind: "diagnostic", detail: "recoverable" });
    expect(applyRuntimeEvent({ runtime, config: null }, event).runtime).toBe(runtime);
  });
});
