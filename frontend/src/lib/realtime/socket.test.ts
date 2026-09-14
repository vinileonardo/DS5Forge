import { describe, expect, it, vi } from "vitest";

import type { RuntimeState } from "../api/contracts";
import type { ApiProtocolError } from "../api/errors";
import { RealtimeSocket, type WebSocketLike } from "./socket";

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
