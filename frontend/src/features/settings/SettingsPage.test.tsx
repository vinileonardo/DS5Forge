import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Config } from "../../lib/api/contracts";
import { api } from "../../lib/api/client";
import { I18nProvider, LOCALE_STORAGE_KEY } from "../../lib/i18n";
import { SettingsPage } from "./SettingsPage";

const model = vi.hoisted(() => ({ value: {} as unknown }));

vi.mock("../../lib/runtime/RuntimeProvider", () => ({
  useRuntime: () => model.value,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

function makeConfig(): Config {
  return {
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
    },
  } as Config;
}

function makeValue(updateConfig: (patch: unknown) => Promise<Config>) {
  return { config: makeConfig(), coreStatus: "online", updateConfig };
}

describe("SettingsPage recovery surfaces", () => {
  it("keeps desktop recovery and signed updates available while the core is offline", async () => {
    model.value = { config: null, coreStatus: "offline", updateConfig: vi.fn() };
    render(<SettingsPage />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeVisible();
    expect(screen.getByText("Core preferences unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: /restart core/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /check for updates/i })).toBeEnabled();
    expect(screen.queryByLabelText("Theme")).not.toBeInTheDocument();
  });

  it("shows a blocking progress surface while a core restart is in flight", async () => {
    model.value = { config: null, coreStatus: "offline", updateConfig: vi.fn() };
    let finishRestart: ((value: Awaited<ReturnType<typeof api.restartCore>>) => void) | undefined;
    vi.spyOn(api, "restartCore").mockImplementation(
      () =>
        new Promise((resolve) => {
          finishRestart = resolve;
        }),
    );
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /restart core/i }));
    expect(screen.getByLabelText("Restarting local core")).toBeVisible();
    expect(screen.getByText("Restarting local core…")).toBeVisible();
    expect(screen.getByRole("button", { name: /restarting/i })).toBeDisabled();

    finishRestart?.({ state: "running", core: "running", pid: null, message: null });
    await waitFor(() => expect(screen.queryByLabelText("Restarting local core")).not.toBeInTheDocument());
  });
});

describe("SettingsPage language selector", () => {
  it("switches the visible page copy live through the global locale store", async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    model.value = makeValue(vi.fn());
    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Desktop" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Startup" })).toBeVisible();
    expect(screen.getByText("Advanced · Remote Access")).toBeInTheDocument();
    expect(screen.getByLabelText("Theme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check for updates/i })).toBeVisible();

    const selector = screen.getByLabelText("Language");
    fireEvent.change(selector, { target: { value: "pt-BR" } });

    expect(await screen.findByRole("heading", { name: "Configurações" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Área de trabalho" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Inicialização" })).toBeVisible();
    expect(screen.getByText("Avançado · Acesso remoto")).toBeInTheDocument();
    expect(screen.getByLabelText("Tema")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /verificar atualizações/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /exportar pacote de suporte/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /salvar configurações/i })).toBeVisible();
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("pt-BR");
  });
});

describe("SettingsPage draft handling", () => {
  it("preserves an unsaved setting across a config refresh", async () => {
    model.value = makeValue(vi.fn());
    const { rerender } = render(<SettingsPage />);
    const theme = await screen.findByLabelText("Theme");
    fireEvent.change(theme, { target: { value: "Light" } });
    expect(theme).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();

    model.value = { ...makeValue(vi.fn()), config: makeConfig() };
    rerender(<SettingsPage />);

    expect(screen.getByLabelText("Theme")).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();
  });

  it("keeps the setting after a rejected save instead of reverting to persisted values", async () => {
    const updateConfig = vi.fn().mockRejectedValue(new Error("server rejected the patch"));
    model.value = makeValue(updateConfig);
    render(<SettingsPage />);
    const theme = await screen.findByLabelText("Theme");
    fireEvent.change(theme, { target: { value: "Light" } });
    fireEvent.click(screen.getByRole("button", { name: /save settings/i }));

    await waitFor(() => expect(updateConfig).toHaveBeenCalled());
    expect(screen.getByLabelText("Theme")).toHaveValue("Light");
    expect(screen.getByText("Unsaved settings")).toBeVisible();
  });
});
