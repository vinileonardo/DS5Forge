import { expect, test, type Page } from "@playwright/test";

const foreground = {
  available: true,
  pid: 4200,
  executable_name: "fixture-game.exe",
  executable_path: "C:\\Games\\fixture-game.exe",
  title: "Fixture Game",
  observed_at: 1_725_000_000,
  process_alive: true,
  diagnostic: null,
};

const game = {
  id: "fixture-game",
  name: "Fixture Game",
  executables: ["fixture-game.exe", "fixture-launcher.exe"],
  executable_path: null,
  profile: "Default",
  compatibility_mode: "native",
  enabled: true,
};

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
  foreground,
  automation: {
    enabled: true,
    exit_policy: "restore_previous",
    default_profile: "Default",
    active_game_id: game.id,
    active_game_name: game.name,
    active_profile: game.profile,
    profile_origin: "automatic",
    manual_override: false,
    last_match: {
      game_id: game.id,
      game_name: game.name,
      matched: true,
      reason: "Executable name and configured path matched.",
      foreground,
    },
    rule_evaluations: [
      {
        game_id: game.id,
        game_name: game.name,
        matched: true,
        reason: "Executable name and configured path matched.",
        action: "activate",
        profile: game.profile,
        compatibility_mode: game.compatibility_mode,
      },
    ],
    previous_profile: "Default",
    previous_compatibility_mode: "native",
    transition: 1,
    last_transition_at: 1_725_000_000,
    status: "active",
    diagnostic: null,
  },
  compatibility: {
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
    changed_at: 1_725_000_000,
  },
  synthetic_outputs: { held: [], last_release: null, release_status: "idle" },
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

const matchResponse = {
  matched: true,
  game_id: game.id,
  game_name: game.name,
  reason: "Executable name and configured path matched.",
  foreground,
  evaluations: state.automation.rule_evaluations,
};

const exclusiveCapability = {
  provider_available: false,
  provider_installed: false,
  virtual_output_reports: false,
  physical_suppression_available: false,
  physical_suppression_verified: false,
  provenance: {
    provider: "none",
    version: null,
    executable: null,
    sha256: null,
    signature_verified: false,
    provenance_verified: false,
    integrity_verified: false,
    windows_validated: false,
    evidence: ["provider not configured"],
  },
  reason: "Exclusive Mode is disabled until a verified Windows provider is available.",
};

const exclusiveStatus = {
  mode: "off",
  enabled: false,
  generation: 0,
  ownership_acquired: false,
  heartbeat_at: 0,
  heartbeat_timeout_ms: 1500,
  stale: false,
  physical_input_visible: true,
  virtual_input_active: false,
  physical_suppression_active: false,
  double_input_risk: true,
  capability: exclusiveCapability,
  reason: null,
  last_error: null,
  mirrored_sequence: 0,
  updated_at: 0,
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
    } else if (url.endsWith("/games") && route.request().method() === "GET") {
      await route.fulfill({ json: { games: [game] } });
    } else if (url.endsWith("/games/candidates")) {
      await route.fulfill({ json: { candidates: [] } });
    } else if (url.endsWith("/mappings")) {
      await route.fulfill({ json: { mappings: [] } });
    } else if (url.endsWith("/chords")) {
      await route.fulfill({ json: { chords: [] } });
    } else if (url.endsWith("/diagnostics/conflicts")) {
      await route.fulfill({ json: { conflicts: [] } });
    } else if (url.endsWith("/exclusive/capabilities")) {
      await route.fulfill({ json: exclusiveCapability });
    } else if (url.endsWith("/exclusive/status")) {
      await route.fulfill({ json: exclusiveStatus });
    } else if (url.endsWith("/test-match")) {
      await route.fulfill({ json: matchResponse });
    } else {
      await route.fulfill({
        status: 404,
        json: { error: { code: "fixture.not_found", message: "fixture route missing" } },
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

test("renders realtime game state, explains the match and keeps Virtual unavailable", async ({ page }) => {
  await mockCore(page);
  await page.goto("/games");

  await expect(page.getByRole("heading", { name: "Games" })).toBeVisible();
  await expect(page.getByText("fixture-game.exe", { exact: true })).toBeVisible();
  await expect(page.getByText("Fixture Game", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Virtual / XInput unavailable", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Game automation")).toBeChecked();

  await page.getByRole("button", { name: "Test match" }).click();
  await expect(
    page.getByText("Matched: Executable name and configured path matched.", { exact: true }),
  ).toBeVisible();
});

test("reconnects the Games realtime projection without reloading the page", async ({ page }) => {
  const socketCount = await mockCore(page, true);
  let loads = 0;
  page.on("load", () => {
    loads += 1;
  });

  await page.goto("/games");
  await expect(page.getByRole("heading", { name: "Games" })).toBeVisible();
  await expect.poll(() => socketCount(), { timeout: 5_000 }).toBeGreaterThan(1);
  expect(loads).toBe(1);
  await expect(page.getByText("Fixture Game", { exact: true }).first()).toBeVisible();
});
