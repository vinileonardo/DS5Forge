import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

const input = {
  square: false,
  triangle: false,
  circle: false,
  cross: true,
  dpad_up: true,
  dpad_down: false,
  dpad_left: false,
  dpad_right: false,
  l1: false,
  r1: true,
  l2_button: false,
  r2_button: true,
  l3: false,
  r3: false,
  options: false,
  share: false,
  ps: false,
  mic_button: false,
  touchpad_button: true,
  l2: 0.42,
  r2: 0.78,
  sticks: { left_x: -0.4, left_y: 0.2, right_x: 0.5, right_y: -0.25 },
  touch0: { active: true, x: 960, y: 540 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: { cross: true, dpad_up: true, r1: true, r2: true, touchpad_button: true },
};

const offEffect = {
  mode: "off",
  start_position: 0,
  end_position: 255,
  force: 0,
  frequency: 0,
  amplitude: 0,
};

const initialState = {
  connection: "connected",
  identity: {
    model: "DualSense",
    serial: "lab-fixture",
    vendor_id: 1356,
    product_id: 3302,
    transport: "usb",
  },
  capabilities: {
    usb: true,
    rumble: true,
    touchpad: true,
    microphone_button: true,
    lightbar: true,
    adaptive_triggers: true,
    availability: {
      usb: { supported: true, available: true, reason: null },
      rumble: { supported: true, available: true, reason: null },
      touchpad: { supported: true, available: true, reason: null },
      microphone_button: { supported: true, available: true, reason: null },
      lightbar: { supported: true, available: true, reason: null },
      adaptive_triggers: { supported: true, available: true, reason: null },
    },
  },
  battery: { level: 86, charging: false },
  motors: { left: 0, right: 0 },
  input,
  telemetry: { input, sequence: 42, timestamp: 1_725_000_000, sample_rate_hz: 30 },
  lightbar: { r: 12, g: 30, b: 80, enabled: true, brightness: 2, pulse: "off" },
  triggers: { left: offEffect, right: offEffect, preview: null },
  haptics_test: null,
  stick_calibration: {
    left_deadzone: 0.08,
    right_deadzone: 0.08,
    left_center_x: 0,
    left_center_y: 0,
    right_center_x: 0,
    right_center_y: 0,
  },
  gesture_config: {
    enabled: true,
    two_finger_scroll: true,
    tap_to_click: true,
    swipe_enabled: true,
    swipe_threshold: 40,
  },
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
  sequence: 9,
  updated_at: 1_725_000_000,
};

const config = {
  schema_version: 1,
  theme: "Dark",
  mic_button: "master",
  rumble: {
    heavy_cutoff_hz: 180,
    texture_center_hz: 300,
    fast_attack_ms: 5,
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
    gestures_enabled: true,
    two_finger_scroll: true,
    swipe_enabled: true,
    swipe_threshold: 40,
  },
};

const profile = {
  schema_version: 2,
  name: "Default",
  rumble: config.rumble,
  lightbar: initialState.lightbar,
  triggers: { left: offEffect, right: offEffect },
  sticks: initialState.stick_calibration,
  touchpad: initialState.gesture_config,
};

type Fixture = {
  socketCount: () => number;
  disconnect: () => void;
};

async function mockControllerCore(page: Page, closeFirstSocket = false): Promise<Fixture> {
  let currentState = structuredClone(initialState);
  let currentProfile = structuredClone(profile);
  let profileSummaries = [
    { name: "Default", source: "bundled", editable: false },
    { name: "Lab Existing", source: "user", editable: true },
  ];
  let socketCount = 0;
  let activeSocket: WebSocketRoute | null = null;

  const send = (payload: unknown) => {
    activeSocket?.send(JSON.stringify({ type: "controller.lab", version: 1, payload }));
  };

  await page.route("http://127.0.0.1:8765/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const body = request.postData()
      ? (JSON.parse(request.postData() as string) as Record<string, unknown>)
      : {};

    if (path === "/api/v1/health") {
      await route.fulfill({ json: { status: "healthy", ...currentState.health } });
      return;
    }
    if (path === "/api/v1/state") {
      await route.fulfill({ json: currentState });
      return;
    }
    if (path === "/api/v1/config") {
      await route.fulfill({ json: config });
      return;
    }
    if (path === "/api/v1/profiles" && request.method() === "GET") {
      await route.fulfill({ json: { profiles: profileSummaries } });
      return;
    }
    if (path === "/api/v1/controller/lightbar" && request.method() === "PUT") {
      currentState = { ...currentState, lightbar: body };
      send({ kind: "lightbar.applied", state: currentState.lightbar });
      await route.fulfill({ json: currentState.lightbar });
      return;
    }
    if (path === "/api/v1/controller/lightbar/reset") {
      currentState = {
        ...currentState,
        lightbar: { r: 0, g: 0, b: 0, enabled: true, brightness: 2, pulse: "off" },
      };
      send({ kind: "lightbar.reset", state: currentState.lightbar });
      await route.fulfill({ json: currentState.lightbar });
      return;
    }
    if (path === "/api/v1/controller/triggers/preview") {
      const preview = {
        id: "preview-fixture",
        status: "running",
        started_at: 1_725_000_000,
        expires_at: 1_725_000_001,
        error: null,
      };
      currentState = { ...currentState, triggers: { ...currentState.triggers, preview } };
      await route.fulfill({ json: preview });
      setTimeout(() => {
        const timedOut = { ...preview, status: "timed_out" };
        currentState = {
          ...currentState,
          triggers: { left: offEffect, right: offEffect, preview: timedOut },
        };
        send({
          kind: "triggers.preview",
          preview: timedOut,
          state: currentState.triggers,
        });
      }, 25);
      return;
    }
    if (path === "/api/v1/controller/triggers" && request.method() === "PUT") {
      currentState = { ...currentState, triggers: { ...body, preview: null } };
      send({ kind: "triggers.applied", state: currentState.triggers });
      await route.fulfill({ json: currentState.triggers });
      return;
    }
    if (path === "/api/v1/controller/triggers/reset") {
      currentState = { ...currentState, triggers: { left: offEffect, right: offEffect, preview: null } };
      send({ kind: "triggers.reset", state: currentState.triggers });
      await route.fulfill({ json: currentState.triggers });
      return;
    }
    if (path === "/api/v1/controller/sticks/calibration/estimate" && request.method() === "POST") {
      await route.fulfill({
        json: {
          samples: Array.isArray(body.samples) ? body.samples.length : 0,
          left: {
            center_x: 0.04,
            center_y: -0.03,
            drift_radius: 0.05,
            jitter_radius: 0.012,
            recommended_deadzone: 0.03,
            samples_used: 60,
            rejected_samples: 0,
          },
          right: {
            center_x: -0.02,
            center_y: 0.01,
            drift_radius: 0.0223606798,
            jitter_radius: 0.008,
            recommended_deadzone: 0.02,
            samples_used: 60,
            rejected_samples: 0,
          },
          recommended_calibration: {
            left_deadzone: 0.03,
            right_deadzone: 0.02,
            left_center_x: 0.04,
            left_center_y: -0.03,
            right_center_x: -0.02,
            right_center_y: 0.01,
          },
        },
      });
      return;
    }
    if (path === "/api/v1/controller/sticks/calibration" && request.method() === "PUT") {
      currentState = { ...currentState, stick_calibration: body };
      send({ kind: "sticks.calibration_changed", state: currentState.stick_calibration });
      await route.fulfill({ json: currentState.stick_calibration });
      return;
    }
    if (path === "/api/v1/profiles/import") {
      await route.fulfill({
        status: 422,
        json: {
          error: {
            code: "profile.invalid",
            message: "Profile import rejected by fixture.",
            detail: null,
            recoverable: true,
            fields: { content: "unknown field" },
          },
        },
      });
      return;
    }
    if (path.startsWith("/api/v1/profiles/") && path.endsWith("/load")) {
      const name = decodeURIComponent(path.split("/").at(-2) ?? "Default");
      await route.fulfill({ json: { profile: name, config, unsupported_sections: [], state: currentState } });
      return;
    }
    if (path.startsWith("/api/v1/profiles/") && request.method() === "GET") {
      await route.fulfill({ json: currentProfile });
      return;
    }
    if (path.startsWith("/api/v1/profiles/") && request.method() === "PUT") {
      const name = decodeURIComponent(path.split("/").at(-1) ?? "Lab E2E");
      delete body.confirm_overwrite;
      currentProfile = { ...body, name };
      profileSummaries = [...profileSummaries, { name, source: "user", editable: true }];
      await route.fulfill({ json: { profile: name, full_profile: currentProfile } });
      return;
    }
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
  });

  await page.routeWebSocket("ws://127.0.0.1:8765/api/v1/ws", (socket) => {
    socketCount += 1;
    activeSocket = socket;
    socket.send(JSON.stringify({ type: "state.snapshot", version: 1, payload: { state: currentState } }));
    if (closeFirstSocket && socketCount === 1) {
      setTimeout(() => socket.close({ code: 1001, reason: "fixture reconnect" }), 120);
    }
  });

  return {
    socketCount: () => socketCount,
    disconnect: () => {
      activeSocket?.send(
        JSON.stringify({
          type: "controller.lifecycle",
          version: 1,
          payload: { state: "disconnected", error: null },
        }),
      );
    },
  };
}

test.describe("Controller Lab", () => {
  test("connects and renders a bounded live input monitor", async ({ page }) => {
    await mockControllerCore(page);
    await page.goto("/controller");

    await expect(page.getByRole("heading", { name: "Controller Lab" })).toBeVisible();
    await expect(page.locator("main .page-header .status-pill")).toContainText("Live");
    await expect(page.getByText("Cross", { exact: true })).toHaveClass(/pressed/);
    await expect(page.getByText("1 / 2 points active", { exact: true })).toBeVisible();
    await expect(page.getByText("42", { exact: true })).toBeVisible();
  });

  test("runs a trigger preview and reflects the automatic neutral reset", async ({ page }) => {
    await mockControllerCore(page);
    await page.goto("/controller");
    await page.getByRole("tab", { name: "Triggers" }).click();

    await page.getByRole("button", { name: "Preview", exact: true }).click();
    await expect(page.getByText("timed out", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Preview active; both triggers will reset automatically.", { exact: true }),
    ).toBeVisible();
  });

  test("applies and resets lightbar state through the local command boundary", async ({ page }) => {
    await mockControllerCore(page);
    await page.goto("/controller");
    await page.getByRole("tab", { name: "Lighting" }).click();

    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText("Lightbar reset.", { exact: true })).toBeVisible();
    await page.getByLabel("Lightbar color").fill("#0a141e");
    await page.getByRole("button", { name: "Apply", exact: true }).click();
    await expect(page.getByText("Lightbar settings applied.", { exact: true })).toBeVisible();
  });

  test("disables output controls when the connected session becomes stale", async ({ page }) => {
    const fixture = await mockControllerCore(page);
    await page.goto("/controller");
    await page.getByRole("tab", { name: "Triggers" }).click();
    fixture.disconnect();

    await expect(page.getByText("Controller state is stale", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Preview", exact: true })).toBeDisabled();
  });

  test("measures drift and applies the recommended stick correction", async ({ page }) => {
    await mockControllerCore(page);
    await page.goto("/controller");
    await page.getByRole("tab", { name: "Sticks" }).click();

    await page.getByRole("button", { name: "Test drift for 3s" }).click();
    await expect(page.getByText("5.0%", { exact: true })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("2.2%", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Apply recommended correction" }).click();
    await expect(page.getByText("Recommended drift correction applied.", { exact: true })).toBeVisible();
    await expect(page.getByText("Left deadzone · 3.0%", { exact: true })).toBeVisible();
    await expect(page.getByText("Right deadzone · 2.0%", { exact: true })).toBeVisible();
  });

  test("saves a full profile and leaves active state unchanged after rejected import", async ({ page }) => {
    await mockControllerCore(page);
    await page.goto("/profiles");

    await page.getByLabel("New user profile name").fill("Lab E2E");
    await page.getByRole("button", { name: "Save profile", exact: true }).click();
    await expect(
      page.getByText("Full Controller Lab profile “Lab E2E” saved.", { exact: true }),
    ).toBeVisible();
    await page
      .locator(".profile-row")
      .filter({ hasText: "Lab E2E" })
      .getByRole("button", { name: "Apply" })
      .click();
    await expect(page.getByText("Profile “Lab E2E” applied.", { exact: true })).toBeVisible();

    const rejected = JSON.stringify({ ...profile, name: "Lab E2E", unexpected: true });
    await page.getByLabel("Import controller profile").setInputFiles({
      name: "rejected.json",
      mimeType: "application/json",
      buffer: Buffer.from(rejected),
    });
    await expect(page.getByText("Profile import rejected by fixture.", { exact: true })).toBeVisible();
    await expect(page.locator(".tag-active")).toHaveText("Active");
  });

  test("reconnects the Controller Lab without a page reload", async ({ page }) => {
    const fixture = await mockControllerCore(page, true);
    let loads = 0;
    page.on("load", () => {
      loads += 1;
    });
    await page.goto("/controller");
    await expect(page.getByRole("heading", { name: "Controller Lab" })).toBeVisible();
    await expect.poll(() => fixture.socketCount(), { timeout: 5_000 }).toBeGreaterThan(1);
    await expect(page.locator("main .page-header .status-pill")).toContainText("Live");
    expect(loads).toBe(1);
  });
});
