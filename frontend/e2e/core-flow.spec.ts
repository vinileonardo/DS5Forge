import { expect, test, type Page } from "@playwright/test";

const state = {
  connection: "connected",
  identity: { model: "DualSense", serial: "fixture", vendor_id: 1356, product_id: 3302, transport: "usb" },
  capabilities: {
    usb: true,
    rumble: true,
    touchpad: true,
    microphone_button: true,
    lightbar: true,
    adaptive_triggers: false,
  },
  battery: { level: 82, charging: false },
  motors: { left: 0, right: 0 },
  rumble_enabled: true,
  touchpad_enabled: true,
  active_profile: "Default",
  config_version: 1,
  audio: { status: "listening", device: "Fixture speakers", error: null },
  last_error: null,
  health: {
    process_alive: true,
    controller_available: true,
    subsystems: { core: "ready", controller: "connected", audio: "listening", touchpad: "ready" },
    degraded: [],
  },
  sequence: 4,
  updated_at: 1_725_000_000,
};

const config = {
  schema_version: 1,
  theme: "Dark",
  mic_button: "master",
  rumble: {
    heavy_cutoff_hz: 180,
    texture_center_hz: 90,
    fast_attack_ms: 30,
    fast_release_ms: 110,
    baseline_attack_ms: 350,
    baseline_release_ms: 1800,
    gate: 0.05,
    impact_level: 0.55,
    gamma: 2.2,
    transient_min_level: 0.22,
    transient_gain: 3,
    transient_weight: 0.6,
    drive_gate: 0.06,
    texture_gate_mult: 1.4,
    min_rumble: 28,
    max_rumble: 255,
  },
  trackpad: {
    trackpad_enabled_on_start: true,
    pointer_speed: 0.75,
    acceleration: 0.006,
    accel_cap: 1.2,
    scroll_speed: 0.35,
    tap_to_click: true,
  },
};

async function mockCore(page: Page, closeFirstSocket = false) {
  let socketCount = 0;
  await page.route("http://127.0.0.1:8765/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/health")) {
      await route.fulfill({ json: { status: "healthy", ...state.health } });
    } else if (url.endsWith("/state")) {
      await route.fulfill({ json: state });
    } else if (url.endsWith("/config")) {
      await route.fulfill({ json: config });
    } else if (url.endsWith("/profiles")) {
      await route.fulfill({ json: { profiles: [{ name: "Default", source: "bundled", editable: false }] } });
    } else if (url.endsWith("/commands/rumble")) {
      await route.fulfill({ json: { ...state, rumble_enabled: false, sequence: 5 } });
    } else {
      await route.fulfill({
        status: 404,
        json: {
          error: {
            code: "fixture.not_found",
            message: "fixture route missing",
            detail: null,
            recoverable: false,
            fields: {},
          },
        },
      });
    }
  });
  await page.routeWebSocket("ws://127.0.0.1:8765/api/v1/ws", (socket) => {
    socketCount += 1;
    socket.send(JSON.stringify({ type: "state.snapshot", version: 1, payload: { state } }));
    if (closeFirstSocket && socketCount === 1) {
      setTimeout(() => void socket.close({ code: 1001, reason: "fixture reconnect" }), 120);
    }
  });
  return () => socketCount;
}

test("bootstraps from HTTP and WebSocket, then confirms a mutation", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("main").getByText("DualSense", { exact: true })).toBeVisible();
  await expect(page.getByText("Local core online", { exact: true }).first()).toBeVisible();

  const haptics = page.getByRole("checkbox", { name: "Haptics", exact: true });
  await expect(haptics).toBeChecked();
  await haptics.click();
  await expect(haptics).not.toBeChecked();
});

test("reconnects the WebSocket without a page reload", async ({ page }) => {
  const socketCount = await mockCore(page, true);
  let loads = 0;
  page.on("load", () => {
    loads += 1;
  });
  await page.goto("/");
  await expect(page.getByRole("main").getByText("DualSense", { exact: true })).toBeVisible();
  await expect.poll(() => socketCount(), { timeout: 5_000 }).toBeGreaterThan(1);
  expect(loads).toBe(1);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});
