import { describe, expect, it } from "vitest";

import {
  AutomationStateSchema,
  ConfigSchema,
  ControllerInputSchema,
  ControllerTelemetrySchema,
  FullControllerProfileSchema,
  RuntimeStateSchema,
} from "./contracts";

const config = {
  schema_version: 1 as const,
  theme: "Dark" as const,
  mic_button: "master" as const,
  rumble: {
    heavy_cutoff_hz: 180,
    texture_center_hz: 90,
    fast_attack_ms: 30,
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
};

describe("P0 runtime contracts", () => {
  it("accepts the schema-v1 config without coercing values", () => {
    expect(ConfigSchema.safeParse(config).success).toBe(true);
    expect(ConfigSchema.safeParse({ ...config, rumble: { ...config.rumble, gate: "0.1" } }).success).toBe(
      false,
    );
    expect(ConfigSchema.safeParse({ ...config, rumble: { ...config.rumble, gate: 2 } }).success).toBe(false);
  });

  it("rejects unknown external fields", () => {
    expect(ConfigSchema.safeParse({ ...config, unexpected: true }).success).toBe(false);
  });

  it("rejects incomplete state snapshots instead of creating frontend defaults", () => {
    expect(RuntimeStateSchema.safeParse({ connection: "connected" }).success).toBe(false);
  });

  it("accepts the backend automation contract when foreground is explicitly null", () => {
    const automation = {
      enabled: false,
      exit_policy: "restore_previous" as const,
      default_profile: "Default",
      active_game_id: null,
      active_game_name: null,
      active_profile: "Default",
      profile_origin: "manual" as const,
      manual_override: false,
      last_match: null,
      rule_evaluations: [],
      previous_profile: null,
      previous_compatibility_mode: null,
      transition: 0,
      last_transition_at: 0,
      status: "idle",
      diagnostic: null,
      foreground: null,
      active_game: null,
    };

    expect(AutomationStateSchema.safeParse(automation).success).toBe(true);
  });

  it("accepts bounded controller telemetry and rejects coercion, non-finite values and unknown fields", () => {
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
      l2: 0.4,
      r2: 0,
      sticks: { left_x: 0.2, left_y: 0, right_x: 0, right_y: -0.2 },
      touch0: { active: true, x: 300, y: 400 },
      touch1: { active: false, x: 0, y: 0 },
      buttons: { cross: true },
    };
    const telemetry = { input, sequence: 2, timestamp: 10, sample_rate_hz: 30 };

    expect(ControllerInputSchema.safeParse(input).success).toBe(true);
    expect(ControllerTelemetrySchema.safeParse(telemetry).success).toBe(true);
    expect(ControllerTelemetrySchema.safeParse({ ...telemetry, timestamp: Number.NaN }).success).toBe(false);
    expect(
      ControllerTelemetrySchema.safeParse({ ...telemetry, input: { ...input, l2: "0.4" } }).success,
    ).toBe(false);
    expect(ControllerTelemetrySchema.safeParse({ ...telemetry, unexpected: true }).success).toBe(false);
  });

  it("keeps full profile contracts strict", () => {
    const profile = {
      schema_version: 2 as const,
      name: "Lab",
      rumble: config.rumble,
      lightbar: { r: 0, g: 0, b: 0, enabled: true, brightness: 2, pulse: "off" as const },
      triggers: {
        left: {
          mode: "off" as const,
          start_position: 0,
          end_position: 255,
          force: 0,
          frequency: 0,
          amplitude: 0,
        },
        right: {
          mode: "off" as const,
          start_position: 0,
          end_position: 255,
          force: 0,
          frequency: 0,
          amplitude: 0,
        },
      },
      sticks: {
        left_deadzone: 0.08,
        right_deadzone: 0.08,
        left_center_x: 0,
        left_center_y: 0,
        right_center_x: 0,
        right_center_y: 0,
      },
      touchpad: {
        enabled: true,
        two_finger_scroll: true,
        tap_to_click: true,
        swipe_enabled: true,
        swipe_threshold: 40,
      },
    };
    expect(FullControllerProfileSchema.safeParse(profile).success).toBe(true);
    expect(FullControllerProfileSchema.safeParse({ ...profile, unexpected: true }).success).toBe(false);
    expect(
      FullControllerProfileSchema.safeParse({ ...profile, lightbar: { ...profile.lightbar, r: "1" } })
        .success,
    ).toBe(false);
  });
});
