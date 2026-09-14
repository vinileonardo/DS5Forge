import { z } from "zod";

const finiteNumber = z.number().finite();
const bounded = (minimum: number, maximum: number) => finiteNumber.min(minimum).max(maximum);

export const ConnectionStateSchema = z.enum([
  "disconnected",
  "connecting",
  "connected",
  "reconnecting",
  "stopping",
  "error",
]);

export const ErrorSnapshotSchema = z
  .object({
    code: z.string(),
    message: z.string(),
    detail: z.string().nullable(),
    recoverable: z.boolean(),
    fields: z.record(z.string(), z.unknown()),
  })
  .strict();

export const HealthStateSchema = z
  .object({
    process_alive: z.boolean(),
    controller_available: z.boolean(),
    subsystems: z.record(z.string(), z.string()),
    degraded: z.array(z.string()),
  })
  .strict();

export const HealthResponseSchema = HealthStateSchema.extend({ status: z.string() }).strict();

export const ControllerIdentitySchema = z
  .object({
    model: z.string(),
    serial: z.string().nullable(),
    vendor_id: z.number().int().nullable(),
    product_id: z.number().int().nullable(),
    transport: z.string(),
  })
  .strict();

export const ControllerCapabilitiesSchema = z
  .object({
    usb: z.boolean(),
    rumble: z.boolean(),
    touchpad: z.boolean(),
    microphone_button: z.boolean(),
    lightbar: z.boolean(),
    adaptive_triggers: z.boolean(),
  })
  .strict();

export const BatterySchema = z
  .object({ level: z.number().int().min(0).max(100), charging: z.boolean().nullable() })
  .strict();

export const MotorSchema = z
  .object({ left: z.number().int().min(0).max(255), right: z.number().int().min(0).max(255) })
  .strict();

export const AudioSchema = z
  .object({ status: z.string(), device: z.string().nullable(), error: z.string().nullable() })
  .strict();

export const RuntimeStateSchema = z
  .object({
    connection: ConnectionStateSchema,
    identity: ControllerIdentitySchema.nullable(),
    capabilities: ControllerCapabilitiesSchema,
    battery: BatterySchema,
    motors: MotorSchema,
    rumble_enabled: z.boolean(),
    touchpad_enabled: z.boolean(),
    active_profile: z.string(),
    config_version: z.number().int(),
    audio: AudioSchema,
    last_error: ErrorSnapshotSchema.nullable(),
    health: HealthStateSchema,
    sequence: z.number().int().nonnegative(),
    updated_at: finiteNumber,
  })
  .strict();

export const RumbleConfigSchema = z
  .object({
    heavy_cutoff_hz: bounded(1, 20_000),
    texture_center_hz: bounded(1, 20_000),
    fast_attack_ms: bounded(0.1, 10_000),
    fast_release_ms: bounded(0.1, 10_000),
    baseline_attack_ms: bounded(0.1, 10_000),
    baseline_release_ms: bounded(0.1, 20_000),
    gate: bounded(0, 1),
    impact_level: bounded(0.001, 1),
    gamma: bounded(0.01, 10),
    transient_min_level: bounded(0, 1),
    transient_gain: bounded(0, 20),
    transient_weight: bounded(0, 1),
    drive_gate: bounded(0, 1),
    texture_gate_mult: bounded(0, 10),
    min_rumble: bounded(0, 255),
    max_rumble: bounded(0, 255),
  })
  .strict();

export const TrackpadConfigSchema = z
  .object({
    trackpad_enabled_on_start: z.boolean(),
    pointer_speed: bounded(0.01, 10),
    acceleration: bounded(0, 1),
    accel_cap: bounded(0, 10),
    scroll_speed: bounded(0.01, 10),
    tap_to_click: z.boolean(),
  })
  .strict();

export const ConfigSchema = z
  .object({
    schema_version: z.literal(1),
    theme: z.enum(["Light", "Dark", "Liquid Glass"]),
    mic_button: z.enum(["master", "rumble", "trackpad"]),
    rumble: RumbleConfigSchema,
    trackpad: TrackpadConfigSchema,
  })
  .strict();

export const ProfileSummarySchema = z
  .object({ name: z.string(), source: z.enum(["bundled", "user"]), editable: z.boolean() })
  .strict();

export const ProfilesResponseSchema = z.object({ profiles: z.array(ProfileSummarySchema) }).strict();
export const ProfileLoadResponseSchema = z.object({ profile: z.string(), config: ConfigSchema }).strict();
export const ProfileSaveResponseSchema = z
  .object({ profile: z.string(), rumble: RumbleConfigSchema })
  .strict();
export const DeleteProfileResponseSchema = z.object({ deleted: z.string() }).strict();
export const RumbleTestResponseSchema = z.object({ accepted: z.boolean() }).strict();

export const EventEnvelopeSchema = z
  .object({ type: z.string(), version: z.number().int(), payload: z.unknown() })
  .strict();

export type ConnectionState = z.infer<typeof ConnectionStateSchema>;
export type ErrorSnapshot = z.infer<typeof ErrorSnapshotSchema>;
export type Audio = z.infer<typeof AudioSchema>;
export type HealthState = z.infer<typeof HealthStateSchema>;
export type HealthResponse = z.infer<typeof HealthResponseSchema>;
export type RuntimeState = z.infer<typeof RuntimeStateSchema>;
export type RumbleConfig = z.infer<typeof RumbleConfigSchema>;
export type TrackpadConfig = z.infer<typeof TrackpadConfigSchema>;
export type Config = z.infer<typeof ConfigSchema>;
export type ProfileSummary = z.infer<typeof ProfileSummarySchema>;

export type RumbleConfigPatch = Partial<RumbleConfig>;
export type TrackpadConfigPatch = Partial<TrackpadConfig>;
export type ConfigPatch = {
  schema_version?: 1;
  theme?: Config["theme"];
  mic_button?: Config["mic_button"];
  rumble?: RumbleConfigPatch;
  trackpad?: TrackpadConfigPatch;
};

export type EventType =
  | "state.snapshot"
  | "state.updated"
  | "controller.lifecycle"
  | "audio.status"
  | "config.changed"
  | "profile.changed"
  | "diagnostic";

export type RuntimeEvent =
  | { type: "state.snapshot"; version: 1; payload: { state: RuntimeState } }
  | { type: "state.updated"; version: 1; payload: { state: RuntimeState } }
  | {
      type: "controller.lifecycle";
      version: 1;
      payload: { state: ConnectionState; error: ErrorSnapshot | null };
    }
  | { type: "audio.status"; version: 1; payload: z.infer<typeof AudioSchema> }
  | { type: "config.changed"; version: 1; payload: { config: Config } }
  | { type: "profile.changed"; version: 1; payload: Record<string, unknown> }
  | { type: "diagnostic"; version: 1; payload: Record<string, unknown> };

export const RUMBLE_FIELD_SPECS: ReadonlyArray<{
  key: keyof RumbleConfig;
  label: string;
  help: string;
  min: number;
  max: number;
  step: number;
  group: string;
}> = [
  {
    key: "heavy_cutoff_hz",
    label: "Heavy cutoff",
    help: "Upper frequency boundary for heavy rumble.",
    min: 1,
    max: 20000,
    step: 1,
    group: "Frequency response",
  },
  {
    key: "texture_center_hz",
    label: "Texture center",
    help: "Center frequency used for texture rumble.",
    min: 1,
    max: 20000,
    step: 1,
    group: "Frequency response",
  },
  {
    key: "fast_attack_ms",
    label: "Fast attack",
    help: "Rise time for short transients, in milliseconds.",
    min: 0.1,
    max: 10000,
    step: 0.1,
    group: "Envelope",
  },
  {
    key: "fast_release_ms",
    label: "Fast release",
    help: "Release time for short transients, in milliseconds.",
    min: 0.1,
    max: 10000,
    step: 0.1,
    group: "Envelope",
  },
  {
    key: "baseline_attack_ms",
    label: "Baseline attack",
    help: "Rise time for sustained energy, in milliseconds.",
    min: 0.1,
    max: 10000,
    step: 0.1,
    group: "Envelope",
  },
  {
    key: "baseline_release_ms",
    label: "Baseline release",
    help: "Release time for sustained energy, in milliseconds.",
    min: 0.1,
    max: 20000,
    step: 0.1,
    group: "Envelope",
  },
  {
    key: "gate",
    label: "Gate",
    help: "Minimum normalized signal level before rumble starts.",
    min: 0,
    max: 1,
    step: 0.01,
    group: "Detection and gating",
  },
  {
    key: "impact_level",
    label: "Impact level",
    help: "Normalized level that shapes impact detection.",
    min: 0.001,
    max: 1,
    step: 0.001,
    group: "Detection and gating",
  },
  {
    key: "drive_gate",
    label: "Drive gate",
    help: "Threshold for drive component detection.",
    min: 0,
    max: 1,
    step: 0.01,
    group: "Detection and gating",
  },
  {
    key: "texture_gate_mult",
    label: "Texture gate multiplier",
    help: "Multiplier applied to texture gating.",
    min: 0,
    max: 10,
    step: 0.1,
    group: "Detection and gating",
  },
  {
    key: "transient_min_level",
    label: "Transient minimum",
    help: "Minimum level for transient shaping.",
    min: 0,
    max: 1,
    step: 0.01,
    group: "Transient shaping",
  },
  {
    key: "transient_gain",
    label: "Transient gain",
    help: "Gain applied to detected transients.",
    min: 0,
    max: 20,
    step: 0.1,
    group: "Transient shaping",
  },
  {
    key: "transient_weight",
    label: "Transient weight",
    help: "Blend between transient and baseline output.",
    min: 0,
    max: 1,
    step: 0.01,
    group: "Transient shaping",
  },
  {
    key: "gamma",
    label: "Gamma",
    help: "Output curve used for motor level shaping.",
    min: 0.01,
    max: 10,
    step: 0.01,
    group: "Output shaping",
  },
  {
    key: "min_rumble",
    label: "Minimum rumble",
    help: "Lowest motor level after gating.",
    min: 0,
    max: 255,
    step: 1,
    group: "Output shaping",
  },
  {
    key: "max_rumble",
    label: "Maximum rumble",
    help: "Highest motor level sent to the controller.",
    min: 0,
    max: 255,
    step: 1,
    group: "Output shaping",
  },
];

export const TRACKPAD_FIELD_SPECS: ReadonlyArray<{
  key: keyof TrackpadConfig;
  label: string;
  help: string;
  min?: number;
  max?: number;
  step?: number;
}> = [
  {
    key: "pointer_speed",
    label: "Pointer speed",
    help: "Base speed for one-finger pointer movement.",
    min: 0.01,
    max: 10,
    step: 0.01,
  },
  {
    key: "acceleration",
    label: "Acceleration",
    help: "Additional pointer acceleration.",
    min: 0,
    max: 1,
    step: 0.001,
  },
  {
    key: "accel_cap",
    label: "Acceleration cap",
    help: "Maximum acceleration contribution.",
    min: 0,
    max: 10,
    step: 0.01,
  },
  {
    key: "scroll_speed",
    label: "Scroll speed",
    help: "Speed for two-finger vertical scrolling.",
    min: 0.01,
    max: 10,
    step: 0.01,
  },
];
