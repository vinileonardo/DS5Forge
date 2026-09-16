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
    case "controller.input":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              input: event.payload.input,
              telemetry: event.payload.telemetry,
            }
          : projection.runtime,
      };
    case "controller.lab":
      if (!projection.runtime) return projection;
      if (event.payload.kind === "lightbar.applied" || event.payload.kind === "lightbar.reset") {
        return { ...projection, runtime: { ...projection.runtime, lightbar: event.payload.state } };
      }
      if (event.payload.kind === "player_leds.applied" || event.payload.kind === "player_leds.reset") {
        return { ...projection, runtime: { ...projection.runtime, player_leds: event.payload.player_leds } };
      }
      if (
        event.payload.kind === "triggers.applied" ||
        event.payload.kind === "triggers.reset" ||
        event.payload.kind === "triggers.preview"
      ) {
        return { ...projection, runtime: { ...projection.runtime, triggers: event.payload.state } };
      }
      if (event.payload.kind === "haptics.test") {
        return { ...projection, runtime: { ...projection.runtime, haptics_test: event.payload.run } };
      }
      if (event.payload.kind === "sticks.calibration_changed") {
        return { ...projection, runtime: { ...projection.runtime, stick_calibration: event.payload.state } };
      }
      return projection;
    case "game.foreground_changed":
      return {
        ...projection,
        runtime: projection.runtime
          ? { ...projection.runtime, foreground: event.payload.foreground }
          : projection.runtime,
      };
    case "game.detected":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              foreground: event.payload.foreground,
              automation: projection.runtime.automation
                ? {
                    ...projection.runtime.automation,
                    last_match: event.payload.match,
                    rule_evaluations: event.payload.evaluations,
                  }
                : projection.runtime.automation,
            }
          : projection.runtime,
      };
    case "compatibility.changed":
      return {
        ...projection,
        runtime: projection.runtime
          ? { ...projection.runtime, compatibility: event.payload.compatibility }
          : projection.runtime,
      };
    case "game.activated":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              active_profile: event.payload.profile,
              compatibility: event.payload.compatibility,
              automation: projection.runtime.automation
                ? {
                    ...projection.runtime.automation,
                    active_game_id: event.payload.game.id,
                    active_game_name: event.payload.game.name,
                    active_profile: event.payload.profile,
                    profile_origin: event.payload.profile_origin,
                    manual_override: false,
                    status: "active",
                    active_game: event.payload.game,
                  }
                : projection.runtime.automation,
            }
          : projection.runtime,
      };
    case "game.deactivated":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              active_profile: event.payload.applied_profile ?? projection.runtime.active_profile,
              automation: projection.runtime.automation
                ? {
                    ...projection.runtime.automation,
                    active_game_id: null,
                    active_game_name: null,
                    active_profile: event.payload.applied_profile ?? projection.runtime.active_profile,
                    active_game: null,
                    manual_override: false,
                  }
                : projection.runtime.automation,
            }
          : projection.runtime,
      };
    case "game.rule_applied":
      return projection;
    case "automation.changed":
      if (!("automation" in event.payload) || !projection.runtime) return projection;
      return {
        ...projection,
        runtime: {
          ...projection.runtime,
          automation: event.payload.automation,
        },
      };
    case "game.conflict_detected":
      return {
        ...projection,
        runtime: projection.runtime
          ? {
              ...projection.runtime,
              conflicts: [
                ...(projection.runtime.conflicts ?? []).filter(
                  (item) => item.process !== event.payload.conflict.process,
                ),
                event.payload.conflict,
              ],
            }
          : projection.runtime,
      };
    case "synthetic.release":
      return projection;
    case "exclusive.changed":
    case "exclusive.recovered":
      return {
        ...projection,
        runtime: projection.runtime
          ? { ...projection.runtime, exclusive: event.payload.exclusive }
          : projection.runtime,
      };
    case "diagnostics.duplicate_input":
      return projection;
    case "adaptive_trigger.changed":
      return projection;
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
    case "controller.input":
      return `Controller input sample ${event.payload.telemetry.sequence}`;
    case "config.changed":
      return "Configuration updated by the core";
    case "profile.changed":
      return `Profile event${typeof event.payload.name === "string" ? `: ${event.payload.name}` : ""}`;
    case "controller.lab":
      return `Controller Lab event${typeof event.payload.kind === "string" ? `: ${event.payload.kind}` : ""}`;
    case "diagnostic":
      return "Core diagnostic event";
    case "game.foreground_changed":
      return `Foreground changed: ${event.payload.foreground.executable_name ?? "desktop"}`;
    case "game.detected":
      return event.payload.match ? "Game rule matched foreground" : "No game rule matched foreground";
    case "game.activated":
      return "Game profile activated";
    case "game.deactivated":
      return "Game profile deactivated";
    case "game.rule_applied":
      return "Game rule evaluation completed";
    case "compatibility.changed":
      return `Compatibility mode: ${event.payload.compatibility.mode}`;
    case "game.conflict_detected":
      return `Possible conflict: ${event.payload.conflict.process}`;
    case "automation.changed":
      return "Game automation changed";
    case "synthetic.release":
      return "Synthetic outputs released";
    case "exclusive.changed":
      return `Exclusive input: ${event.payload.exclusive.mode}`;
    case "exclusive.recovered":
      return "Exclusive input stale state recovered";
    case "diagnostics.duplicate_input":
      return `Duplicate-input risk: ${event.payload.diagnostic.severity}`;
    case "adaptive_trigger.changed":
      return "Adaptive trigger source changed";
  }
}

function diagnosticDetail(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const error = value as Partial<ErrorSnapshot>;
  return typeof error.message === "string" ? error.message : undefined;
}
