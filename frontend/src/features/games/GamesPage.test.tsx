import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GamesPage } from "./GamesPage";

const apiMock = vi.hoisted(() => ({
  games: vi.fn(),
  mappings: vi.fn(),
  chords: vi.fn(),
  conflictDiagnostics: vi.fn(),
  addGame: vi.fn(),
  updateGame: vi.fn(),
  deleteGame: vi.fn(),
  testGameMatch: vi.fn(),
  updateAutomation: vi.fn(),
  updateCompatibility: vi.fn(),
  updateMappings: vi.fn(),
  updateChords: vi.fn(),
}));

const model = vi.hoisted(() => ({ value: {} as unknown }));

vi.mock("../../lib/api/client", () => ({ api: apiMock }));
vi.mock("../../lib/runtime/RuntimeProvider", () => ({
  useRuntime: () => model.value,
  formatRuntimeError: (error: unknown) => (error instanceof Error ? error.message : "request failed"),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const game = {
  id: "fixture-game",
  name: "Fixture Game",
  executables: ["game.exe", "launcher.exe"],
  executable_path: null,
  profile: "Default",
  compatibility_mode: "native" as const,
  enabled: true,
};

function makeRuntime() {
  return {
    connection: "connected",
    identity: null,
    capabilities: {
      usb: true,
      rumble: true,
      touchpad: true,
      microphone_button: true,
      lightbar: true,
      adaptive_triggers: false,
    },
    battery: { level: 80, charging: false },
    motors: { left: 0, right: 0 },
    active_profile: "Default",
    config_version: 1,
    audio: { status: "stopped", device: null, error: null },
    last_error: null,
    health: { process_alive: true, controller_available: true, subsystems: {}, degraded: [] },
    sequence: 2,
    updated_at: 100,
    foreground: {
      available: true,
      pid: 42,
      executable_name: "game.exe",
      executable_path: "C:\\Games\\game.exe",
      title: "Fixture title",
      observed_at: 100,
      process_alive: true,
      diagnostic: null,
    },
    automation: {
      enabled: true,
      exit_policy: "restore_previous" as const,
      default_profile: "Default",
      active_game_id: "fixture-game",
      active_game_name: "Fixture Game",
      active_profile: "Default",
      profile_origin: "automatic" as const,
      manual_override: false,
      last_match: { reason: "Executable name and configured path matched." },
      rule_evaluations: [],
      previous_profile: "Default",
      previous_compatibility_mode: "native" as const,
      transition: 1,
      last_transition_at: 100,
      status: "active",
      diagnostic: null,
    },
    compatibility: {
      mode: "native" as const,
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
      changed_at: 100,
    },
    synthetic_outputs: { held: [], last_release: null, release_status: "idle" },
  };
}

function setupApi() {
  apiMock.games.mockResolvedValue({ games: [game] });
  apiMock.mappings.mockResolvedValue({ mappings: [] });
  apiMock.chords.mockResolvedValue({ chords: [] });
  apiMock.conflictDiagnostics.mockResolvedValue({ conflicts: [] });
  apiMock.updateAutomation.mockResolvedValue(makeRuntime().automation);
  apiMock.updateCompatibility.mockResolvedValue(makeRuntime().compatibility);
  apiMock.testGameMatch.mockResolvedValue({
    matched: true,
    game_id: game.id,
    game_name: game.name,
    reason: "Executable name and configured path matched.",
    foreground: makeRuntime().foreground,
    evaluations: [],
  });
}

describe("GamesPage", () => {
  it("renders realtime foreground/active-game state, explains a match and keeps Virtual unavailable", async () => {
    setupApi();
    model.value = {
      runtime: makeRuntime(),
      coreStatus: "online",
      stale: false,
      loading: false,
    };

    render(<GamesPage />);

    expect(await screen.findByRole("heading", { name: "Games" })).toBeVisible();
    expect(screen.getAllByText("Fixture Game")[0]).toBeVisible();
    expect(screen.getAllByText(/game\.exe, launcher\.exe/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Executable name and configured path matched.")).toBeVisible();
    expect(screen.getByText("Virtual / XInput unavailable", { exact: true })).toBeVisible();
    expect(screen.getByLabelText("Game automation")).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Rule ID")).toBeDisabled();
    expect(screen.getByLabelText("Optional full path")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Test match" }));
    await waitFor(() => expect(apiMock.testGameMatch).toHaveBeenCalledWith("fixture-game"));
    expect(await screen.findByText("Matched: Executable name and configured path matched.")).toBeVisible();
  });

  it("keeps mapping/chord ids immutable, removes them through full-list updates and warns on running conflicts", async () => {
    setupApi();
    apiMock.mappings.mockResolvedValue({
      mappings: [
        {
          id: "cross-space",
          input: "cross",
          output_kind: "keyboard",
          output_code: "SPACE",
          game_id: null,
          enabled: true,
          debounce_ms: 25,
        },
      ],
    });
    apiMock.chords.mockResolvedValue({
      chords: [
        {
          id: "shoulders-escape",
          inputs: ["l1", "r1"],
          output_kind: "keyboard",
          output_code: "ESC",
          game_id: null,
          enabled: true,
          window_ms: 250,
          debounce_ms: 25,
        },
      ],
    });
    apiMock.conflictDiagnostics.mockResolvedValue({
      conflicts: [
        {
          process: "steam.exe",
          running: true,
          severity: "warning",
          message: "Steam is running. Steam Input may affect this game depending on its configuration.",
          evidence: "Process name was observed; Steam Input activity was not proven.",
          checked_at: 100,
        },
      ],
    });
    apiMock.updateMappings.mockResolvedValue({ mappings: [] });
    apiMock.updateChords.mockResolvedValue({ chords: [] });
    model.value = {
      runtime: {
        ...makeRuntime(),
        compatibility: {
          ...makeRuntime().compatibility,
          mode: "remap" as const,
          double_input_risk: true,
          reason:
            "Remap adds keyboard/mouse output while the physical controller remains visible; the game may also react.",
        },
      },
      coreStatus: "online",
      stale: false,
      loading: false,
    };

    render(<GamesPage />);
    expect(await screen.findByRole("heading", { name: "Mappings" })).toBeVisible();

    const mappingsCard = screen.getByRole("heading", { name: "Mappings" }).closest(".card") as HTMLElement;
    fireEvent.click(within(mappingsCard).getByRole("button", { name: "Edit" }));
    expect(within(mappingsCard).getByLabelText("Mapping ID")).toBeDisabled();
    fireEvent.click(within(mappingsCard).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(apiMock.updateMappings).toHaveBeenCalledWith([]));

    const chordsCard = screen.getByRole("heading", { name: "Chords" }).closest(".card") as HTMLElement;
    fireEvent.click(within(chordsCard).getByRole("button", { name: "Edit" }));
    expect(within(chordsCard).getByLabelText("Chord ID")).toBeDisabled();
    fireEvent.click(within(chordsCard).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(apiMock.updateChords).toHaveBeenCalledWith([]));

    expect(screen.getByText("warning", { exact: true })).toHaveClass("status-warning");
    expect(screen.getByText("Possible double input in Remap", { exact: true })).toBeVisible();
  });

  it("disables automation while the projection is stale and exposes the offline state", async () => {
    setupApi();
    model.value = {
      runtime: makeRuntime(),
      coreStatus: "offline",
      stale: true,
      loading: false,
    };

    render(<GamesPage />);

    expect(await screen.findByText("Local core offline", { exact: true })).toBeVisible();
    expect(screen.getByLabelText("Game automation")).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Input mode" })).toBeDisabled();
  });
});
