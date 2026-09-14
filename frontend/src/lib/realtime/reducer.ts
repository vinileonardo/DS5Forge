import {
  type Audio,
  type Config,
  type ErrorSnapshot,
  type RuntimeEvent,
  type RuntimeState,
} from "../api/contracts";

export type SessionEvent = {
  id: number;
  at: number;
  kind: string;
  summary: string;
  detail?: string;
};

export type RuntimeProjection = {
  runtime: RuntimeState | null;
  config: Config | null;
};

export function applyRuntimeEvent(projection: RuntimeProjection, event: RuntimeEvent): RuntimeProjection {
  switch (event.type) {
    case "state.snapshot":
    case "state.updated":
      return { ...projection, runtime: event.payload.state };
    case "config.changed":
      return { ...projection, config: event.payload.config };
    case "controller.lifecycle":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              connection: event.payload.state,
              last_error: event.payload.error,
              health: {
                ...projection.runtime.health,
                controller_available: event.payload.state === "connected",
                subsystems: { ...projection.runtime.health.subsystems, controller: event.payload.state },
              },
            }
          : projection.runtime,
      };
    case "audio.status":
      return {
        ...projection,
        runtime: projection.runtime ? updateAudio(projection.runtime, event.payload) : projection.runtime,
      };
    case "profile.changed":
    case "diagnostic":
      return projection;
  }
}

function updateAudio(runtime: RuntimeState, audio: Audio): RuntimeState {
  const degraded = new Set(runtime.health.degraded);
  if (audio.status === "error") degraded.add("audio");
  else if (audio.status === "listening" || audio.status === "stopped") degraded.delete("audio");
  return {
    ...runtime,
    audio,
    health: {
      ...runtime.health,
      degraded: [...degraded].sort(),
      subsystems: { ...runtime.health.subsystems, audio: audio.status },
    },
  };
}

export function sessionEventFor(event: RuntimeEvent, nextId: number): SessionEvent {
  const detail = event.type === "diagnostic" ? diagnosticDetail(event.payload.error) : undefined;
  return {
    id: nextId,
    at: Date.now(),
    kind: event.type,
    summary: eventSummary(event),
    ...(detail ? { detail } : {}),
  };
}

function eventSummary(event: RuntimeEvent): string {
  switch (event.type) {
    case "state.snapshot":
      return "Authoritative state snapshot received";
    case "state.updated":
      return `Runtime state updated (sequence ${event.payload.state.sequence})`;
    case "controller.lifecycle":
      return `Controller lifecycle: ${event.payload.state}`;
    case "audio.status":
      return `Audio capture: ${event.payload.status}`;
    case "config.changed":
      return "Configuration updated by the core";
    case "profile.changed":
      return `Profile event${typeof event.payload.name === "string" ? `: ${event.payload.name}` : ""}`;
    case "diagnostic":
      return "Core diagnostic event";
  }
}

function diagnosticDetail(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const error = value as Partial<ErrorSnapshot>;
  return typeof error.message === "string" ? error.message : undefined;
}
