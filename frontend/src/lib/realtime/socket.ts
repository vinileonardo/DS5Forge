import { z } from "zod";

import {
  AudioSchema,
  ConfigSchema,
  CompatibilityStateSchema,
  ConflictDiagnosticSchema,
  ControllerLabEventSchema,
  ControllerInputSchema,
  ControllerTelemetrySchema,
  ConnectionStateSchema,
  ErrorSnapshotSchema,
  EventEnvelopeSchema,
  ExclusiveStatusSchema,
  DuplicateInputDiagnosticSchema,
  ForegroundApplicationSchema,
  GameActivatedEventSchema,
  GameDeactivatedEventSchema,
  GameMatchSchema,
  GameRuleAppliedEventSchema,
  RuleEvaluationSchema,
  ReleaseReportSchema,
  RuntimeStateSchema,
  AutomationChangedEventSchema,
  type RuntimeEvent,
} from "../api/contracts";
import { ApiProtocolError } from "../api/errors";

export type SocketStatus = "online" | "reconnecting" | "offline" | "protocol_error";
export type WebSocketLike = {
  binaryType: BinaryType;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  onerror: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  close: (code?: number, reason?: string) => void;
};
export type WebSocketFactory = (url: string) => WebSocketLike;

const KNOWN_TYPES = new Set([
  "state.snapshot",
  "state.updated",
  "controller.input",
  "controller.lifecycle",
  "audio.status",
  "config.changed",
  "profile.changed",
  "controller.lab",
  "diagnostic",
  "game.foreground_changed",
  "game.detected",
  "game.activated",
  "game.deactivated",
  "game.rule_applied",
  "compatibility.changed",
  "game.conflict_detected",
  "automation.changed",
  "synthetic.release",
  "exclusive.changed",
  "exclusive.recovered",
  "diagnostics.duplicate_input",
  "adaptive_trigger.changed",
]);
const KNOWN_LAB_KINDS = new Set([
  "lightbar.applied",
  "lightbar.reset",
  "player_leds.applied",
  "player_leds.reset",
  "triggers.applied",
  "triggers.reset",
  "triggers.preview",
  "haptics.test",
  "sticks.calibration_changed",
]);

export type ParsedSocketMessage = { kind: "event"; event: RuntimeEvent } | { kind: "unknown"; type: string };

export function parseSocketMessage(value: unknown): ParsedSocketMessage {
  const envelope = EventEnvelopeSchema.parse(value);
  if (envelope.version !== 1) {
    if (KNOWN_TYPES.has(envelope.type)) {
      throw new ApiProtocolError(`Unsupported version ${envelope.version} for ${envelope.type}.`);
    }
    return { kind: "unknown", type: envelope.type };
  }
  switch (envelope.type) {
    case "state.snapshot":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ state: RuntimeStateSchema }).strict().parse(envelope.payload),
        },
      };
    case "state.updated":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ state: RuntimeStateSchema }).strict().parse(envelope.payload),
        },
      };
    case "controller.input":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z
            .object({ input: ControllerInputSchema, telemetry: ControllerTelemetrySchema })
            .strict()
            .parse(envelope.payload),
        },
      };
    case "controller.lifecycle":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z
            .object({ state: ConnectionStateSchema, error: ErrorSnapshotSchema.nullable() })
            .strict()
            .parse(envelope.payload),
        },
      };
    case "audio.status":
      return {
        kind: "event",
        event: { type: envelope.type, version: 1, payload: AudioSchema.parse(envelope.payload) },
      };
    case "config.changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ config: ConfigSchema }).strict().parse(envelope.payload),
        },
      };
    case "profile.changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.record(z.string(), z.unknown()).parse(envelope.payload),
        },
      };
    case "controller.lab": {
      const kind =
        typeof envelope.payload === "object" && envelope.payload !== null && "kind" in envelope.payload
          ? (envelope.payload as { kind?: unknown }).kind
          : undefined;
      const parsed = ControllerLabEventSchema.safeParse(envelope.payload);
      if (!parsed.success) {
        // A new lab kind can be ignored without making an otherwise valid
        // v1 socket unusable. Existing kinds remain strict/protocol-trusted.
        if (typeof kind === "string" && !KNOWN_LAB_KINDS.has(kind)) {
          return { kind: "unknown", type: envelope.type };
        }
        throw parsed.error;
      }
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: parsed.data,
        },
      };
    }
    case "diagnostic":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.record(z.string(), z.unknown()).parse(envelope.payload),
        },
      };
    case "game.foreground_changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z
            .object({
              foreground: ForegroundApplicationSchema,
              changed: z.boolean(),
              previous: ForegroundApplicationSchema,
            })
            .strict()
            .parse(envelope.payload),
        },
      };
    case "game.detected":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z
            .object({
              match: GameMatchSchema.nullable(),
              evaluations: z.array(RuleEvaluationSchema),
              foreground: ForegroundApplicationSchema,
            })
            .strict()
            .parse(envelope.payload),
        },
      };
    case "game.activated":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: GameActivatedEventSchema.parse(envelope.payload),
        },
      };
    case "game.deactivated":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: GameDeactivatedEventSchema.parse(envelope.payload),
        },
      };
    case "game.rule_applied":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: GameRuleAppliedEventSchema.parse(envelope.payload),
        },
      };
    case "automation.changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: AutomationChangedEventSchema.parse(envelope.payload),
        },
      };
    case "compatibility.changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ compatibility: CompatibilityStateSchema }).strict().parse(envelope.payload),
        },
      };
    case "game.conflict_detected":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ conflict: ConflictDiagnosticSchema }).strict().parse(envelope.payload),
        },
      };
    case "synthetic.release":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ report: ReleaseReportSchema }).strict().parse(envelope.payload),
        },
      };
    case "exclusive.changed":
    case "exclusive.recovered":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ exclusive: ExclusiveStatusSchema }).strict().parse(envelope.payload),
        },
      };
    case "diagnostics.duplicate_input":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.object({ diagnostic: DuplicateInputDiagnosticSchema }).strict().parse(envelope.payload),
        },
      };
    case "adaptive_trigger.changed":
      return {
        kind: "event",
        event: {
          type: envelope.type,
          version: 1,
          payload: z.record(z.string(), z.unknown()).parse(envelope.payload),
        },
      };
    default:
      return { kind: "unknown", type: envelope.type };
  }
}

export type RealtimeSocketOptions = {
  url: string;
  createWebSocket?: WebSocketFactory;
  onStatus: (status: SocketStatus) => void;
  onEvent: (event: RuntimeEvent) => void;
  onProtocolError: (error: ApiProtocolError) => void;
  onReconnect: (recovered: boolean) => void;
  onUnknownEvent?: (type: string) => void;
  random?: () => number;
  setTimeoutFn?: typeof window.setTimeout;
  clearTimeoutFn?: typeof window.clearTimeout;
};

export class RealtimeSocket {
  private socket: WebSocketLike | null = null;
  private timer: number | undefined;
  private attempt = 0;
  private everOnline = false;
  private awaitingSnapshot = true;
  private protocolFault = false;
  private stopped = true;
  private readonly options: Required<
    Pick<RealtimeSocketOptions, "createWebSocket" | "random" | "setTimeoutFn" | "clearTimeoutFn">
  > &
    RealtimeSocketOptions;

  constructor(options: RealtimeSocketOptions) {
    this.options = {
      ...options,
      createWebSocket: options.createWebSocket ?? ((url) => new WebSocket(url)),
      random: options.random ?? Math.random,
      setTimeoutFn: options.setTimeoutFn ?? window.setTimeout.bind(window),
      clearTimeoutFn: options.clearTimeoutFn ?? window.clearTimeout.bind(window),
    };
  }

  connect(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.open();
  }

  close(): void {
    this.stopped = true;
    if (this.timer !== undefined) this.options.clearTimeoutFn(this.timer);
    this.timer = undefined;
    this.socket?.close(1000, "client shutdown");
    this.socket = null;
  }

  get reconnectAttempt(): number {
    return this.attempt;
  }

  private open(): void {
    if (this.stopped) return;
    this.options.onStatus(this.everOnline ? "reconnecting" : "offline");
    this.awaitingSnapshot = true;
    const socket = this.options.createWebSocket(this.options.url);
    this.socket = socket;
    socket.binaryType = "blob";
    socket.onopen = () => {
      // Opening the TCP/WebSocket transport is not enough to trust stale
      // controller state. P0 guarantees that the first frame is a validated
      // state.snapshot, so stay offline/reconnecting until that frame arrives.
      this.protocolFault = false;
    };
    socket.onmessage = (message) => this.handleMessage(message.data);
    socket.onerror = () => {
      // onclose owns retry scheduling; this callback only keeps the error
      // visible in browser devtools without treating it as controller state.
    };
    socket.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      this.options.onStatus(
        this.protocolFault ? "protocol_error" : this.everOnline ? "reconnecting" : "offline",
      );
      this.scheduleReconnect();
    };
  }

  private handleMessage(raw: unknown): void {
    try {
      const value = typeof raw === "string" ? JSON.parse(raw) : raw;
      const parsed = parseSocketMessage(value);
      if (this.awaitingSnapshot) {
        if (parsed.kind !== "event" || parsed.event.type !== "state.snapshot") {
          throw new ApiProtocolError("The first WebSocket frame must be a state.snapshot event.");
        }
        const recovered = this.everOnline || this.attempt > 0;
        this.awaitingSnapshot = false;
        this.everOnline = true;
        this.attempt = 0;
        this.options.onEvent(parsed.event);
        this.options.onStatus("online");
        // HTTP bootstrap may have raced a core that was offline. Refresh after
        // every validated socket bootstrap so config/profiles converge too.
        this.options.onReconnect(recovered);
        return;
      }
      if (parsed.kind === "event") this.options.onEvent(parsed.event);
      else this.options.onUnknownEvent?.(parsed.type);
    } catch (error) {
      const protocolError =
        error instanceof ApiProtocolError
          ? error
          : new ApiProtocolError("The WebSocket payload is invalid.", error);
      this.protocolFault = true;
      this.options.onProtocolError(protocolError);
      this.options.onStatus("protocol_error");
      this.socket?.close(1002, "protocol error");
    }
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.timer !== undefined) return;
    const exponent = Math.min(this.attempt, 4);
    const base = Math.min(8_000, 500 * 2 ** exponent);
    const jitter = 0.85 + this.options.random() * 0.3;
    this.attempt += 1;
    this.timer = this.options.setTimeoutFn(
      () => {
        this.timer = undefined;
        this.open();
      },
      Math.round(base * jitter),
    );
  }
}
