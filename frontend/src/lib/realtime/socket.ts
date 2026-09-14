import { z } from "zod";

import {
  AudioSchema,
  ConfigSchema,
  ConnectionStateSchema,
  ErrorSnapshotSchema,
  EventEnvelopeSchema,
  RuntimeStateSchema,
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
  "controller.lifecycle",
  "audio.status",
  "config.changed",
  "profile.changed",
  "diagnostic",
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
    case "diagnostic":
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
