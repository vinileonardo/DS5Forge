import { describe, expect, it, vi } from "vitest";

import type { RuntimeState } from "../api/contracts";
import type { ApiProtocolError } from "../api/errors";
import { RealtimeSocket, parseSocketMessage, type WebSocketLike } from "./socket";

const runtime = {
  connection: "disconnected",
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
  health: { process_alive: true, controller_available: false, subsystems: {}, degraded: [] },
  sequence: 0,
  updated_at: 0,
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
  sticks: { left_x: 0.1, left_y: 0, right_x: 0, right_y: -0.1 },
  touch0: { active: false, x: 0, y: 0 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: { cross: true },
};

class FakeSocket implements WebSocketLike {
  binaryType: BinaryType = "blob";
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close = vi.fn(() => this.onclose?.(new CloseEvent("close")));
}

describe("realtime WebSocket client", () => {
  it("trusts the connection only after the initial snapshot and ignores later unknown event types", () => {
    const socket = new FakeSocket();
    const events: unknown[] = [];
    const unknown: string[] = [];
    const statuses: string[] = [];
    const readyStates: boolean[] = [];
    const client = new RealtimeSocket({
      url: "ws://127.0.0.1:8765/api/v1/ws",
      createWebSocket: () => socket,
      onStatus: (status) => statuses.push(status),
      onEvent: (event) => events.push(event),
      onProtocolError: () => undefined,
      onReconnect: (recovered) => readyStates.push(recovered),
      onUnknownEvent: (type) => unknown.push(type),
    });
    client.connect();
    socket.onopen?.(new Event("open"));
    expect(statuses).toEqual(["offline"]);
    socket.onmessage?.({
      data: JSON.stringify({ type: "state.snapshot", version: 1, payload: { state: runtime } }),
    } as MessageEvent);
    socket.onmessage?.({
      data: JSON.stringify({ type: "future.event", version: 9, payload: {} }),
    } as MessageEvent);
    expect(events).toHaveLength(1);
    expect(statuses).toEqual(["offline", "online"]);
    expect(readyStates).toEqual([false]);
    expect(unknown).toEqual(["future.event"]);
    client.close();
  });

  it("parses the bounded controller input event and rejects extra payload fields", () => {
    const parsed = parseSocketMessage({
      type: "controller.input",
      version: 1,
      payload: { input, telemetry: { input, sequence: 4, timestamp: 2, sample_rate_hz: 30 } },
    });
    expect(parsed.kind).toBe("event");
    if (parsed.kind === "event") expect(parsed.event.type).toBe("controller.input");

    expect(() =>
      parseSocketMessage({
        type: "controller.input",
        version: 1,
        payload: {
          input: { ...input, unexpected: true },
          telemetry: { input, sequence: 4, timestamp: 2, sample_rate_hz: 30 },
        },
      }),
    ).toThrow();
  });

  it("parses P3 foreground/game events with strict match and compatibility contracts", () => {
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
    const parsed = parseSocketMessage({
      type: "game.detected",
      version: 1,
      payload: {
        match: {
          game_id: "game",
          game_name: "Game",
          matched: true,
          reason: "Executable name and configured path matched.",
          foreground,
        },
        evaluations: [],
        foreground,
      },
    });
    expect(parsed.kind).toBe("event");
    if (parsed.kind === "event" && parsed.event.type === "game.detected") {
      expect(parsed.event.payload.match?.game_id).toBe("game");
    }

    expect(() =>
      parseSocketMessage({
        type: "game.detected",
        version: 1,
        payload: { match: { game_id: "game" }, evaluations: [], foreground },
      }),
    ).toThrow();

    const compatibility = {
      mode: "native",
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
    expect(
      parseSocketMessage({
        type: "compatibility.changed",
        version: 1,
        payload: { compatibility },
      }),
    ).toMatchObject({ kind: "event", event: { type: "compatibility.changed" } });

    expect(
      parseSocketMessage({
        type: "synthetic.release",
        version: 1,
        payload: {
          report: {
            reason: "game_change",
            released: [{ kind: "keyboard", code: "CTRL+S" }],
            failures: [],
            completed: true,
          },
        },
      }),
    ).toMatchObject({ kind: "event", event: { type: "synthetic.release" } });
    expect(() =>
      parseSocketMessage({
        type: "synthetic.release",
        version: 1,
        payload: {
          report: {
            reason: "game_change",
            released: [],
            failures: [],
            completed: true,
            unexpected: true,
          },
        },
      }),
    ).toThrow();
  });

  it("parses known lab events strictly and ignores future lab kinds", () => {
    const lightbar = {
      r: 10,
      g: 20,
      b: 30,
      enabled: true,
      brightness: 2,
      pulse: "off" as const,
    };
    const parsed = parseSocketMessage({
      type: "controller.lab",
      version: 1,
      payload: { kind: "lightbar.applied", state: lightbar },
    });
    expect(parsed.kind).toBe("event");
    expect(
      parseSocketMessage({
        type: "controller.lab",
        version: 1,
        payload: { kind: "future.lab", state: lightbar },
      }),
    ).toEqual({ kind: "unknown", type: "controller.lab" });
    expect(() =>
      parseSocketMessage({
        type: "controller.lab",
        version: 1,
        payload: { kind: "lightbar.applied", state: { ...lightbar, extra: true } },
      }),
    ).toThrow();
  });

  it("rejects a non-snapshot first frame as a protocol error", () => {
    const socket = new FakeSocket();
    const errors: ApiProtocolError[] = [];
    const client = new RealtimeSocket({
      url: "ws://local",
      createWebSocket: () => socket,
      onStatus: () => undefined,
      onEvent: () => undefined,
      onProtocolError: (error) => errors.push(error),
      onReconnect: () => undefined,
    });
    client.connect();
    socket.onopen?.(new Event("open"));
    socket.onmessage?.({
      data: JSON.stringify({
        type: "controller.lifecycle",
        version: 1,
        payload: { state: "connected", error: null },
      }),
    } as MessageEvent);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toContain("first WebSocket frame");
    client.close();
  });

  it("surfaces a known version mismatch as a protocol error", () => {
    const socket = new FakeSocket();
    const errors: ApiProtocolError[] = [];
    const client = new RealtimeSocket({
      url: "ws://local",
      createWebSocket: () => socket,
      onStatus: () => undefined,
      onEvent: () => undefined,
      onProtocolError: (error) => errors.push(error),
      onReconnect: () => undefined,
    });
    client.connect();
    socket.onmessage?.({
      data: JSON.stringify({ type: "state.snapshot", version: 2, payload: { state: runtime } }),
    } as MessageEvent);
    expect(errors).toHaveLength(1);
    client.close();
  });
});
