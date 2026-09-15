import { z } from "zod";

import {
  ConfigSchema,
  AutomationStateSchema,
  ChordsResponseSchema,
  CompatibilityStateSchema,
  ConflictDiagnosticsResponseSchema,
  type ConfigPatch,
  ControllerTelemetrySchema,
  ForegroundApplicationSchema,
  GameDefinitionSchema,
  GameMatchResponseSchema,
  GamesResponseSchema,
  FullControllerProfileSchema,
  GestureConfigSchema,
  HapticsTestRunSchema,
  LightbarSchema,
  MappingsResponseSchema,
  DeleteProfileResponseSchema,
  HealthResponseSchema,
  ProfileLoadResponseSchema,
  ProfileSaveResponseSchema,
  ProfilesResponseSchema,
  RumbleTestResponseSchema,
  RuntimeStateSchema,
  StickCalibrationSchema,
  TriggerPreviewSchema,
  TriggerStateSchema,
  type AutomationState,
  type Chord,
  type CompatibilityState,
  type ConflictDiagnostic,
  type ForegroundApplication,
  type GameDefinition,
  type Mapping,
  type ControllerProfile,
  type ControllerTelemetry,
  type GestureConfig,
  type LightbarState,
  type RumbleConfig,
  type RuntimeState,
  type StickCalibration,
  type TriggerEffect,
} from "./contracts";
import { ApiError, ApiProtocolError } from "./errors";

export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8765/api/v1";

function validateApiBaseUrl(raw: string | undefined): string {
  const candidate = raw?.trim() || DEFAULT_API_BASE_URL;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch (error) {
    throw new ApiProtocolError("The configured API URL is not valid.", error);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname)
  ) {
    throw new ApiProtocolError("The DS5Forge API URL must point to a local loopback host.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new ApiProtocolError("The DS5Forge API URL may not contain credentials or query parameters.");
  }
  return candidate.replace(/\/$/, "");
}

export const API_BASE_URL = validateApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export function websocketUrl(apiBaseUrl = API_BASE_URL): string {
  const parsed = new URL(apiBaseUrl);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  parsed.pathname = `${parsed.pathname.replace(/\/$/, "")}/ws`;
  return parsed.toString();
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    throw new ApiProtocolError("The local core returned invalid JSON.", error);
  }
}

async function request<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const body = await readBody(response);
  if (!response.ok) {
    const parsed = z.object({ error: z.unknown() }).safeParse(body);
    const errorPayload = parsed.success ? parsed.data.error : body;
    const safeError = z
      .object({
        code: z.string(),
        message: z.string(),
        detail: z.string().nullable().optional().default(null),
        recoverable: z.boolean().optional().default(true),
        fields: z.record(z.string(), z.unknown()).optional().default({}),
      })
      .safeParse(errorPayload);
    if (!safeError.success)
      throw new ApiProtocolError(`The local core returned HTTP ${response.status}.`, safeError.error);
    throw new ApiError(response.status, safeError.data);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success)
    throw new ApiProtocolError(`The local core returned an invalid response for ${path}.`, parsed.error);
  return parsed.data;
}

const json = (value: unknown): RequestInit => ({ method: "PATCH", body: JSON.stringify(value) });
const jsonPut = (value: unknown): RequestInit => ({ method: "PUT", body: JSON.stringify(value) });
const jsonPost = (value?: unknown): RequestInit => ({
  method: "POST",
  ...(value === undefined ? {} : { body: JSON.stringify(value) }),
});

export const api = {
  health: () => request("/health", HealthResponseSchema),
  state: () => request("/state", RuntimeStateSchema),
  games: () => request("/games", GamesResponseSchema),
  addGame: (game: GameDefinition) =>
    request("/games", GameDefinitionSchema, {
      ...jsonPost(game),
      headers: { "Content-Type": "application/json" },
    }),
  getGame: (id: string) => request(`/games/${encodeURIComponent(id)}`, GameDefinitionSchema),
  updateGame: (id: string, game: GameDefinition) =>
    request(`/games/${encodeURIComponent(id)}`, GameDefinitionSchema, {
      ...jsonPut(game),
      headers: { "Content-Type": "application/json" },
    }),
  deleteGame: (id: string) =>
    request(`/games/${encodeURIComponent(id)}`, z.object({ deleted: z.string() }).strict(), {
      method: "DELETE",
    }),
  activeGame: () =>
    request(
      "/games/active",
      z
        .object({ game: GameDefinitionSchema.nullable(), automation: z.record(z.string(), z.unknown()) })
        .strict(),
    ),
  foreground: () => request<ForegroundApplication>("/foreground", ForegroundApplicationSchema),
  automation: () => request<AutomationState>("/automation", AutomationStateSchema),
  updateAutomation: (patch: Partial<Pick<AutomationState, "enabled" | "exit_policy" | "default_profile">>) =>
    request<AutomationState>("/automation", AutomationStateSchema, {
      ...jsonPut(patch),
      headers: { "Content-Type": "application/json" },
    }),
  compatibility: () => request<CompatibilityState>("/compatibility", CompatibilityStateSchema),
  updateCompatibility: (mode: CompatibilityState["mode"]) =>
    request<CompatibilityState>("/compatibility", CompatibilityStateSchema, {
      ...jsonPut({ mode }),
      headers: { "Content-Type": "application/json" },
    }),
  mappings: () => request("/mappings", MappingsResponseSchema),
  updateMappings: (mappings: Mapping[]) =>
    request("/mappings", MappingsResponseSchema, {
      ...jsonPut({ mappings }),
      headers: { "Content-Type": "application/json" },
    }),
  chords: () => request("/chords", ChordsResponseSchema),
  updateChords: (chords: Chord[]) =>
    request("/chords", ChordsResponseSchema, {
      ...jsonPut({ chords }),
      headers: { "Content-Type": "application/json" },
    }),
  testGameMatch: (id: string) =>
    request(`/games/${encodeURIComponent(id)}/test-match`, GameMatchResponseSchema, jsonPost()),
  conflictDiagnostics: () =>
    request<{ conflicts: ConflictDiagnostic[] }>("/diagnostics/conflicts", ConflictDiagnosticsResponseSchema),
  config: () => request("/config", ConfigSchema),
  updateConfig: (patch: ConfigPatch) => request("/config", ConfigSchema, json(patch)),
  profiles: () => request("/profiles", ProfilesResponseSchema),
  loadProfile: (name: string) =>
    request(`/profiles/${encodeURIComponent(name)}/load`, ProfileLoadResponseSchema, { method: "POST" }),
  saveProfile: (name: string, rumble: Partial<RumbleConfig>) =>
    request(`/profiles/${encodeURIComponent(name)}`, ProfileSaveResponseSchema, {
      method: "PUT",
      body: JSON.stringify(rumble),
      headers: { "Content-Type": "application/json" },
    }),
  deleteProfile: (name: string) =>
    request(`/profiles/${encodeURIComponent(name)}`, DeleteProfileResponseSchema, { method: "DELETE" }),
  setRumble: (enabled: boolean) =>
    request<RuntimeState>("/commands/rumble", RuntimeStateSchema, {
      method: "POST",
      body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    }),
  setTouchpad: (enabled: boolean) =>
    request("/commands/touchpad", RuntimeStateSchema, {
      method: "POST",
      body: JSON.stringify({ enabled }),
      headers: { "Content-Type": "application/json" },
    }),
  testRumble: (payload: { left?: number; right?: number; duration_ms?: number } = {}) =>
    request("/commands/rumble/test", RumbleTestResponseSchema, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
    }),
  controllerTelemetry: () => request<ControllerTelemetry>("/controller/telemetry", ControllerTelemetrySchema),
  lightbar: () => request<LightbarState>("/controller/lightbar", LightbarSchema),
  applyLightbar: (state: LightbarState) =>
    request("/controller/lightbar", LightbarSchema, {
      ...jsonPut(state),
      headers: { "Content-Type": "application/json" },
    }),
  resetLightbar: () => request("/controller/lightbar/reset", LightbarSchema, jsonPost()),
  triggers: () => request("/controller/triggers", TriggerStateSchema),
  applyTriggers: (state: { left: TriggerEffect; right: TriggerEffect }) =>
    request("/controller/triggers", TriggerStateSchema, {
      ...jsonPut(state),
      headers: { "Content-Type": "application/json" },
    }),
  previewTriggers: (state: { left: TriggerEffect; right: TriggerEffect; duration_ms: number }) =>
    request("/controller/triggers/preview", TriggerPreviewSchema, {
      ...jsonPost(state),
      headers: { "Content-Type": "application/json" },
    }),
  cancelTriggerPreview: () =>
    request("/controller/triggers/preview", TriggerPreviewSchema.nullable(), { method: "DELETE" }),
  resetTriggers: () => request("/controller/triggers/reset", TriggerStateSchema, jsonPost()),
  startHapticsTest: (payload: { left: number; right: number; duration_ms: number }) =>
    request("/controller/haptics/test", HapticsTestRunSchema, {
      ...jsonPost(payload),
      headers: { "Content-Type": "application/json" },
    }),
  cancelHapticsTest: () =>
    request("/controller/haptics/test", HapticsTestRunSchema.nullable(), { method: "DELETE" }),
  stickCalibration: () => request("/controller/sticks/calibration", StickCalibrationSchema),
  updateStickCalibration: (calibration: StickCalibration) =>
    request("/controller/sticks/calibration", StickCalibrationSchema, {
      ...jsonPut(calibration),
      headers: { "Content-Type": "application/json" },
    }),
  gestures: () => request("/controller/gestures", GestureConfigSchema),
  updateGestures: (patch: Partial<GestureConfig>) =>
    request("/controller/gestures", GestureConfigSchema, {
      ...json({ ...patch }),
      headers: { "Content-Type": "application/json" },
    }),
  getProfile: (name: string) => request(`/profiles/${encodeURIComponent(name)}`, FullControllerProfileSchema),
  saveControllerProfile: (name: string, profile: ControllerProfile, confirmOverwrite = false) =>
    request(`/profiles/${encodeURIComponent(name)}`, ProfileSaveResponseSchema, {
      ...jsonPut({ ...profile, name, confirm_overwrite: confirmOverwrite }),
      headers: { "Content-Type": "application/json" },
    }),
  importProfile: (content: string, name?: string, confirmOverwrite = false) =>
    request("/profiles/import", FullControllerProfileSchema, {
      ...jsonPost({ content, ...(name ? { name } : {}), confirm_overwrite: confirmOverwrite }),
      headers: { "Content-Type": "application/json" },
    }),
};

export type ApiClient = typeof api;
