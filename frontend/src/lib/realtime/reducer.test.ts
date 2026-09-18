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

const input = {
  square: false,
  triangle: false,
  circle: false,
  cross: true,
  dpad_up: false,
  dpad_down: false,
  dpad_left: false,
  dpad_right: false,
  l1: false,
  r1: false,
  l2_button: false,
  r2_button: false,
  l3: false,
  r3: false,
  options: false,
  share: false,
  ps: false,
  mic_button: false,
  touchpad_button: false,
  l2: 0.5,
  r2: 0,
  sticks: { left_x: 0.25, left_y: 0, right_x: 0, right_y: -0.25 },
  touch0: { active: false, x: 0, y: 0 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: { cross: true },
};

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

  it("projects validated controller input without replacing the authoritative snapshot", () => {
    const next = applyRuntimeEvent(
      { runtime, config: null },
      {
        type: "controller.input",
        version: 1,
        payload: { input, telemetry: { input, sequence: 8, timestamp: 4, sample_rate_hz: 30 } },
      },
    );
    expect(next.runtime?.input).toBe(input);
    expect(next.runtime?.telemetry?.sequence).toBe(8);
    expect(next.runtime?.connection).toBe("disconnected");
  });

  it("projects Controller Lab output events, including automatic trigger reset state", () => {
    const next = applyRuntimeEvent(
      { runtime, config: null },
      {
        type: "controller.lab",
        version: 1,
        payload: {
          kind: "triggers.preview",
          preview: {
            id: "preview-1",
            status: "timed_out",
            started_at: 1,
            expires_at: 2,
            error: null,
          },
          state: {
            left: { mode: "off", start_position: 0, end_position: 255, force: 0, frequency: 0, amplitude: 0 },
            right: {
              mode: "off",
              start_position: 0,
              end_position: 255,
              force: 0,
              frequency: 0,
              amplitude: 0,
            },
            preview: {
              id: "preview-1",
              status: "timed_out",
              started_at: 1,
              expires_at: 2,
              error: null,
            },
          },
        },
      },
    );
    expect(next.runtime?.triggers?.preview?.status).toBe("timed_out");
    expect(next.runtime?.triggers?.left.mode).toBe("off");
  });

  it("projects realtime game activation and foreground detection without a reload", () => {
    const foreground = {
      available: true,
      pid: 42,
      executable_name: "game.exe",
      executable_path: "C:\\Games\\game.exe",
      title: "Game",
      observed_at: 10,
      process_alive: true,
      diagnostic: null,
    };
    const game = {
      id: "game",
      name: "Game",
      executables: ["game.exe", "launcher.exe"],
      executable_path: null,
      profile: "Game",
      compatibility_mode: "native" as const,
      adaptive_trigger_mode: "native" as const,
      adaptive_trigger_strength: 45,
      enabled: true,
    };
    const compatibility = {
      mode: "native" as const,
      available: true,
      virtual_capability: {
        installed: false,
        available: false,
        physical_suppression_supported: false,
        provider: null,
        reason: "No approved virtual-controller provider is installed.",
      },
      physical_input_visible: true,
      virtual_input_active: false,
      physical_suppression_active: false,
      double_input_risk: false,
      reason: null,
      changed_at: 10,
    };
    const observed = applyRuntimeEvent(
      {
        runtime: {
          ...runtime,
          automation: {
            enabled: true,
            exit_policy: "restore_previous",
            default_profile: "Default",
            active_game_id: null,
            active_game_name: null,
            active_profile: "Default",
            profile_origin: "manual",
            manual_override: false,
            last_match: null,
            rule_evaluations: [],
            previous_profile: null,
            previous_compatibility_mode: null,
            transition: 0,
            last_transition_at: 0,
            status: "enabled",
            diagnostic: null,
          },
          compatibility,
        },
        config: null,
      },
      {
        type: "game.foreground_changed",
        version: 1,
        payload: {
          foreground,
          changed: true,
          previous: {
            available: true,
            pid: null,
            executable_name: null,
            executable_path: null,
            title: null,
            observed_at: 9,
            process_alive: false,
            diagnostic: null,
          },
        },
      },
    );
    const next = applyRuntimeEvent(observed, {
      type: "game.activated",
      version: 1,
      payload: { game, profile: "Game", profile_origin: "automatic", compatibility },
    });
    expect(observed.runtime?.foreground?.executable_name).toBe("game.exe");
    expect(next.runtime?.automation?.active_game_id).toBe("game");
    expect(next.runtime?.active_profile).toBe("Game");
    expect(next.runtime?.automation?.active_game?.name).toBe("Game");
  });

  it("projects process-name conflict evidence from realtime events", () => {
    const next = applyRuntimeEvent(
      { runtime, config: null },
      {
        type: "game.conflict_detected",
        version: 1,
        payload: {
          conflict: {
            process: "steam.exe",
            running: true,
            severity: "warning",
            message: "Steam is running. Steam Input may affect this game depending on its configuration.",
            evidence: "Process name was observed; Steam Input activity was not proven.",
            checked_at: 10,
          },
        },
      },
    );
    expect(next.runtime?.conflicts?.[0].process).toBe("steam.exe");
  });
});
