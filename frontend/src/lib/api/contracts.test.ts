import { describe, expect, it } from "vitest";

import { ConfigSchema, RuntimeStateSchema } from "./contracts";

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
});
