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
    availability: z
      .record(
        z.string(),
        z.object({ supported: z.boolean(), available: z.boolean(), reason: z.string().nullable() }).strict(),
      )
      .optional()
      .default({}),
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

export const TouchPointSchema = z.object({ active: z.boolean(), x: finiteNumber, y: finiteNumber }).strict();

export const StickTelemetrySchema = z
  .object({
    left_x: bounded(-1, 1),
    left_y: bounded(-1, 1),
    right_x: bounded(-1, 1),
    right_y: bounded(-1, 1),
  })
  .strict();

const defaultControllerInput = () => ({
  square: false,
  triangle: false,
  circle: false,
  cross: false,
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
  l2: 0,
  r2: 0,
  sticks: { left_x: 0, left_y: 0, right_x: 0, right_y: 0 },
  touch0: { active: false, x: 0, y: 0 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: {},
});

export const ControllerInputSchema = z
  .object({
    square: z.boolean(),
    triangle: z.boolean(),
    circle: z.boolean(),
    cross: z.boolean(),
    dpad_up: z.boolean(),
    dpad_down: z.boolean(),
    dpad_left: z.boolean(),
    dpad_right: z.boolean(),
    l1: z.boolean(),
    r1: z.boolean(),
    l2_button: z.boolean(),
    r2_button: z.boolean(),
    l3: z.boolean(),
    r3: z.boolean(),
    options: z.boolean(),
    share: z.boolean(),
    ps: z.boolean(),
    mic_button: z.boolean(),
    touchpad_button: z.boolean(),
    l2: bounded(0, 1),
    r2: bounded(0, 1),
    sticks: StickTelemetrySchema,
    touch0: TouchPointSchema,
    touch1: TouchPointSchema,
    buttons: z.record(z.string(), z.boolean()),
  })
  .strict();

export const ControllerTelemetrySchema = z
  .object({
    input: ControllerInputSchema,
    sequence: z.number().int().nonnegative(),
    timestamp: finiteNumber,
    sample_rate_hz: bounded(0, 1000),
  })
  .strict();

export const LightbarSchema = z
  .object({
    r: z.number().int().min(0).max(255),
    g: z.number().int().min(0).max(255),
    b: z.number().int().min(0).max(255),
    enabled: z.boolean(),
    brightness: z.number().int().min(0).max(2),
    pulse: z.enum(["off", "slow", "fast"]),
  })
  .strict();

export const TriggerEffectSchema = z
  .object({
    mode: z.enum(["off", "resistance", "pulse", "rigid"]),
    start_position: z.number().int().min(0).max(255),
    end_position: z.number().int().min(0).max(255),
    force: z.number().int().min(0).max(255),
    frequency: z.number().int().min(0).max(255),
    amplitude: z.number().int().min(0).max(255),
  })
  .strict();

export const TriggerPreviewSchema = z
  .object({
    id: z.string(),
    status: z.string(),
    started_at: finiteNumber,
    expires_at: finiteNumber,
    error: z
      .object({
        code: z.string(),
        message: z.string(),
        detail: z.string().nullable(),
        recoverable: z.boolean(),
        fields: z.record(z.string(), z.unknown()),
      })
      .strict()
      .nullable(),
  })
  .strict();

export const TriggerStateSchema = z
  .object({ left: TriggerEffectSchema, right: TriggerEffectSchema, preview: TriggerPreviewSchema.nullable() })
  .strict();

export const StickCalibrationSchema = z
  .object({
    left_deadzone: bounded(0, 1),
    right_deadzone: bounded(0, 1),
    left_center_x: bounded(-1, 1),
    left_center_y: bounded(-1, 1),
    right_center_x: bounded(-1, 1),
    right_center_y: bounded(-1, 1),
  })
  .strict();

export const GestureConfigSchema = z
  .object({
    enabled: z.boolean(),
    two_finger_scroll: z.boolean(),
    tap_to_click: z.boolean(),
    swipe_enabled: z.boolean(),
    swipe_threshold: bounded(1, 500),
  })
  .strict();

export const HapticsTestRunSchema = z
  .object({
    id: z.string(),
    status: z.string(),
    left: z.number().int().min(0).max(255),
    right: z.number().int().min(0).max(255),
    duration_ms: z.number().int().min(10).max(5000),
    started_at: finiteNumber,
    expires_at: finiteNumber,
    error: ErrorSnapshotSchema.nullable(),
  })
  .strict();

const LabLightbarEventSchema = z
  .object({
    kind: z.enum(["lightbar.applied", "lightbar.reset"]),
    state: LightbarSchema,
  })
  .strict();

const LabTriggerEventSchema = z
  .object({
    kind: z.enum(["triggers.applied", "triggers.reset", "triggers.preview"]),
    state: TriggerStateSchema,
    preview: TriggerPreviewSchema.optional(),
  })
  .strict();

const LabHapticsEventSchema = z
  .object({
    kind: z.literal("haptics.test"),
    run: HapticsTestRunSchema,
  })
  .strict();

const LabSticksEventSchema = z
  .object({
    kind: z.literal("sticks.calibration_changed"),
    state: StickCalibrationSchema,
  })
  .strict();

export const ControllerLabEventSchema = z.union([
  LabLightbarEventSchema,
  LabTriggerEventSchema,
  LabHapticsEventSchema,
  LabSticksEventSchema,
]);

export const RuntimeStateSchema = z
  .object({
    connection: ConnectionStateSchema,
    identity: ControllerIdentitySchema.nullable(),
    capabilities: ControllerCapabilitiesSchema,
    battery: BatterySchema,
    motors: MotorSchema,
    input: ControllerInputSchema.optional().default(defaultControllerInput()),
    telemetry: ControllerTelemetrySchema.optional().default({
      input: defaultControllerInput(),
      sequence: 0,
      timestamp: 0,
      sample_rate_hz: 30,
    }),
    lightbar: LightbarSchema.optional().default({
      r: 0,
      g: 0,
      b: 0,
      enabled: true,
      brightness: 2,
      pulse: "off",
    }),
    triggers: TriggerStateSchema.optional().default({
      left: { mode: "off", start_position: 0, end_position: 255, force: 0, frequency: 0, amplitude: 0 },
      right: { mode: "off", start_position: 0, end_position: 255, force: 0, frequency: 0, amplitude: 0 },
      preview: null,
    }),
    haptics_test: HapticsTestRunSchema.nullable().optional().default(null),
    stick_calibration: StickCalibrationSchema.optional().default({
      left_deadzone: 0.08,
      right_deadzone: 0.08,
      left_center_x: 0,
      left_center_y: 0,
      right_center_x: 0,
      right_center_y: 0,
    }),
    gesture_config: GestureConfigSchema.optional().default({
      enabled: true,
      two_finger_scroll: true,
      tap_to_click: true,
      swipe_enabled: true,
      swipe_threshold: 40,
    }),
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
    gestures_enabled: z.boolean().optional().default(true),
    two_finger_scroll: z.boolean().optional().default(true),
    swipe_enabled: z.boolean().optional().default(true),
    swipe_threshold: bounded(1, 500).optional().default(40),
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
export const FullControllerProfileSchema = z
  .object({
    schema_version: z.literal(2),
    name: z.string(),
    rumble: RumbleConfigSchema,
    lightbar: LightbarSchema,
    triggers: z.object({ left: TriggerEffectSchema, right: TriggerEffectSchema }).strict(),
    sticks: StickCalibrationSchema,
    touchpad: GestureConfigSchema,
  })
  .strict();

export const ProfileLoadResponseSchema = z
  .object({
    profile: z.string(),
    config: ConfigSchema,
    unsupported_sections: z.array(z.string()).optional().default([]),
    state: RuntimeStateSchema.nullable().optional().default(null),
  })
  .strict();
export const ProfileSaveResponseSchema = z
  .object({
    profile: z.string(),
    rumble: RumbleConfigSchema.nullable().optional(),
    full_profile: FullControllerProfileSchema.nullable().optional(),
  })
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
// Input typing keeps the client compatible with P0/P1 snapshots while the
// schema parser supplies defaults for newly introduced Controller Lab fields.
export type RuntimeState = z.input<typeof RuntimeStateSchema>;
export type TouchPoint = z.infer<typeof TouchPointSchema>;
export type StickTelemetry = z.infer<typeof StickTelemetrySchema>;
export type ControllerInput = z.infer<typeof ControllerInputSchema>;
export type ControllerTelemetry = z.infer<typeof ControllerTelemetrySchema>;
export type LightbarState = z.infer<typeof LightbarSchema>;
export type TriggerEffect = z.infer<typeof TriggerEffectSchema>;
export type TriggerState = z.infer<typeof TriggerStateSchema>;
export type TriggerPreview = z.infer<typeof TriggerPreviewSchema>;
export type HapticsTestRun = z.infer<typeof HapticsTestRunSchema>;
export type StickCalibration = z.infer<typeof StickCalibrationSchema>;
export type GestureConfig = z.infer<typeof GestureConfigSchema>;
export type ControllerProfile = z.infer<typeof FullControllerProfileSchema>;
export type ProfileLoadResponse = z.infer<typeof ProfileLoadResponseSchema>;
export type ProfileSaveResponse = z.infer<typeof ProfileSaveResponseSchema>;
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
  | "controller.input"
  | "controller.lifecycle"
  | "audio.status"
  | "config.changed"
  | "profile.changed"
  | "controller.lab"
  | "diagnostic";

export type RuntimeEvent =
  | { type: "state.snapshot"; version: 1; payload: { state: RuntimeState } }
  | { type: "state.updated"; version: 1; payload: { state: RuntimeState } }
  | {
      type: "controller.input";
      version: 1;
      payload: { input: ControllerInput; telemetry: ControllerTelemetry };
    }
  | {
      type: "controller.lifecycle";
      version: 1;
      payload: { state: ConnectionState; error: ErrorSnapshot | null };
    }
  | { type: "audio.status"; version: 1; payload: z.infer<typeof AudioSchema> }
  | { type: "config.changed"; version: 1; payload: { config: Config } }
  | { type: "profile.changed"; version: 1; payload: Record<string, unknown> }
  | { type: "controller.lab"; version: 1; payload: z.infer<typeof ControllerLabEventSchema> }
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
