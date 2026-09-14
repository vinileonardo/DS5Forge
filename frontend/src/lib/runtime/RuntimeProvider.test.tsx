import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RuntimeState } from "../api/contracts";
import { RuntimeProvider, useRuntime } from "./RuntimeProvider";

afterEach(cleanup);

type SocketCallbacks = {
  onStatus: (status: string) => void;
  onEvent: (event: unknown) => void;
  onProtocolError: (error: unknown) => void;
  onReconnect: (recovered: boolean) => void;
  onUnknownEvent?: (type: string) => void;
};

const mocks = vi.hoisted(() => ({
  socket: null as null | { options: SocketCallbacks; reconnectAttempt: number },
  api: {
    health: vi.fn(),
    state: vi.fn(),
    config: vi.fn(),
    profiles: vi.fn(),
    setRumble: vi.fn(),
    setTouchpad: vi.fn(),
  },
}));

vi.mock("../realtime/socket", () => ({
  RealtimeSocket: class {
    reconnectAttempt = 1;
    options: SocketCallbacks;
    constructor(options: SocketCallbacks) {
      this.options = options;
      mocks.socket = this;
    }
    connect() {}
    close() {}
  },
}));

vi.mock("../api/client", () => ({
  api: mocks.api,
  websocketUrl: () => "ws://127.0.0.1:8765/api/v1/ws",
}));

const baseRuntime = {
  connection: "disconnected",
  identity: null,
  capabilities: {
    usb: true,
    rumble: true,
    touchpad: true,
    microphone_button: true,
    lightbar: true,
    adaptive_triggers: true,
  },
  battery: { level: 100, charging: false },
  motors: { left: 0, right: 0 },
  rumble_enabled: true,
  touchpad_enabled: true,
  active_profile: "Default",
  config_version: 1,
  audio: { status: "stopped", device: null, error: null },
  last_error: null,
  health: { process_alive: true, controller_available: false, subsystems: {}, degraded: [] },
  sequence: 1,
  updated_at: 1,
};

const disconnectedRuntime = { ...baseRuntime, connection: "disconnected" } as unknown as RuntimeState;
const connectedRuntime = {
  ...baseRuntime,
  connection: "connected",
  health: { ...baseRuntime.health, controller_available: true },
} as unknown as RuntimeState;

function Probe() {
  const { stale, coreStatus, canControl, setRumble } = useRuntime();
  return (
    <div>
      <span data-testid="stale">{String(stale)}</span>
      <span data-testid="status">{coreStatus}</span>
      <span data-testid="can-control">{String(canControl)}</span>
      <button onClick={() => void setRumble(true)}>command</button>
    </div>
  );
}

async function mountProvider(state: RuntimeState = disconnectedRuntime) {
  mocks.api.state.mockResolvedValue(state);
  render(
    <RuntimeProvider>
      <Probe />
    </RuntimeProvider>,
  );
  await waitFor(() => expect(mocks.socket).not.toBeNull());
}

async function deliverSnapshot(state: RuntimeState, status: "online" | "reconnecting" = "online") {
  await act(async () => {
    mocks.socket!.options.onEvent({ type: "state.snapshot", version: 1, payload: { state } });
    mocks.socket!.options.onStatus(status);
  });
}

beforeEach(() => {
  mocks.api.health.mockResolvedValue({
    status: "healthy",
    process_alive: true,
    controller_available: false,
    subsystems: {},
    degraded: [],
  });
  mocks.api.state.mockResolvedValue(disconnectedRuntime);
  mocks.api.config.mockResolvedValue(null);
  mocks.api.profiles.mockResolvedValue({ profiles: [] });
  mocks.api.setRumble.mockReset();
  mocks.api.setTouchpad.mockReset();
});

describe("RuntimeProvider stale trust boundary", () => {
  it("keeps state stale when the transport is online but the snapshot is disconnected", async () => {
    await mountProvider();
    await deliverSnapshot(disconnectedRuntime);

    expect(screen.getByTestId("status")).toHaveTextContent("online");
    expect(screen.getByTestId("stale")).toHaveTextContent("true");
    expect(screen.getByTestId("can-control")).toHaveTextContent("false");
  });

  it("marks state fresh when the validated snapshot reports a connected controller", async () => {
    await mountProvider(connectedRuntime);
    await deliverSnapshot(connectedRuntime);

    expect(screen.getByTestId("stale")).toHaveTextContent("false");
    expect(screen.getByTestId("can-control")).toHaveTextContent("true");
  });

  it("does not hard-code fresh state for a disconnected command response", async () => {
    await mountProvider(connectedRuntime);
    await deliverSnapshot(connectedRuntime);
    expect(screen.getByTestId("stale")).toHaveTextContent("false");

    mocks.api.setRumble.mockResolvedValue(disconnectedRuntime);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "command" }));
    });

    await waitFor(() => expect(mocks.api.setRumble).toHaveBeenCalledWith(true));
    await waitFor(() => expect(screen.getByTestId("stale")).toHaveTextContent("true"));
    expect(screen.getByTestId("can-control")).toHaveTextContent("false");
  });

  it("keeps fresh state for a connected command response", async () => {
    await mountProvider(connectedRuntime);
    await deliverSnapshot(connectedRuntime);

    mocks.api.setRumble.mockResolvedValue(connectedRuntime);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "command" }));
    });

    await waitFor(() => expect(mocks.api.setRumble).toHaveBeenCalledWith(true));
    expect(screen.getByTestId("stale")).toHaveTextContent("false");
  });
});
