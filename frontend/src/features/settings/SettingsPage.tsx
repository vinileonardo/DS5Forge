import {
  Check,
  Download,
  KeyRound,
  MonitorCog,
  Palette,
  Power,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  LoadingState,
  Notice,
  PageHeader,
  Select,
} from "../../components/ui";
import type { Config } from "../../lib/api/contracts";
import { api, API_BASE_URL } from "../../lib/api/client";
import { useI18n } from "../../lib/i18n";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";

const themes: Config["theme"][] = ["Dark", "Light", "Liquid Glass"];
const micBehaviors: Config["mic_button"][] = ["master", "rumble", "trackpad"];

type SettingsDraft = Pick<Config, "theme" | "mic_button">;

export function SettingsPage() {
  const { config, coreStatus, updateConfig } = useRuntime();
  const { locale, setLocale, t } = useI18n();
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [appInfo, setAppInfo] = useState<{ version: string; platform: string } | null>(null);
  const [lifecycle, setLifecycle] = useState<{ state: string; core: string } | null>(null);
  const [remote, setRemote] = useState<Awaited<ReturnType<typeof api.remoteStatus>> | null>(null);
  const [tunnel, setTunnel] = useState<Awaited<ReturnType<typeof api.tunnelStatus>> | null>(null);
  const [tunnelExecutable, setTunnelExecutable] = useState("");
  const [tunnelConfigPath, setTunnelConfigPath] = useState("");
  const [tunnelBusy, setTunnelBusy] = useState(false);
  const [pairing, setPairing] = useState<{ code: string; expires_at: number } | null>(null);
  const [origin, setOrigin] = useState("");
  const [autostart, setAutostart] = useState(false);
  const [autostartSupported, setAutostartSupported] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateReady, setUpdateReady] = useState(false);
  const [restartBusy, setRestartBusy] = useState(false);
  const [restartStatus, setRestartStatus] = useState(() => t("settings.restartingStatus"));

  const dirty = Boolean(
    config && draft && (config.theme !== draft.theme || config.mic_button !== draft.mic_button),
  );

  function themeLabel(theme: Config["theme"]): string {
    if (theme === "Dark") return t("settings.themeDark");
    if (theme === "Light") return t("settings.themeLight");
    return t("settings.themeLiquidGlass");
  }

  function micLabel(value: Config["mic_button"]): string {
    if (value === "master") return t("settings.micMasterLabel");
    if (value === "rumble") return t("settings.micRumbleLabel");
    return t("settings.micTrackpadLabel");
  }

  function micHelp(value: Config["mic_button"]): string {
    if (value === "master") return t("settings.micMasterHelp");
    if (value === "rumble") return t("settings.micRumbleHelp");
    return t("settings.micTrackpadHelp");
  }

  useEffect(() => {
    if (config && !dirty) setDraft({ theme: config.theme, mic_button: config.mic_button });
  }, [config, dirty]);

  useEffect(() => {
    let mounted = true;
    void import("@tauri-apps/plugin-autostart")
      .then(async ({ isEnabled }) => {
        const enabled = await isEnabled();
        if (mounted) {
          setAutostart(enabled);
          setAutostartSupported(true);
        }
      })
      .catch(() => {
        if (mounted) setAutostartSupported(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (coreStatus !== "online") return;
    let mounted = true;
    void Promise.allSettled([api.appInfo(), api.lifecycle(), api.remoteStatus(), api.tunnelStatus()]).then(
      ([info, state, remoteState, tunnelState]) => {
        if (!mounted) return;
        if (info.status === "fulfilled") setAppInfo(info.value);
        if (state.status === "fulfilled") setLifecycle(state.value);
        if (remoteState.status === "fulfilled") setRemote(remoteState.value);
        if (tunnelState.status === "fulfilled") setTunnel(tunnelState.value);
      },
    );
    return () => {
      mounted = false;
    };
  }, [coreStatus]);

  async function save() {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      if (!draft) throw new Error(t("settings.coreSettingsUnavailable"));
      const saved = await updateConfig({
        theme: draft.theme,
        mic_button: draft.mic_button,
      });
      setDraft({ theme: saved.theme, mic_button: saved.mic_button });
      setMessage(t("settings.saved"));
    } catch (reason) {
      setError(reason);
    } finally {
      setSaving(false);
    }
  }

  async function toggleAutostart(enabled: boolean) {
    setError(null);
    try {
      const module = await import("@tauri-apps/plugin-autostart");
      if (enabled) await module.enable();
      else await module.disable();
      setAutostart(enabled);
      setMessage(enabled ? t("settings.autostartEnabled") : t("settings.autostartDisabled"));
    } catch (reason) {
      setError(reason);
    }
  }

  async function restartCore() {
    setRestartBusy(true);
    setRestartStatus(t("settings.stoppingCore"));
    setMessage(null);
    setError(null);
    try {
      const isTauriShell =
        window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost";
      if (isTauriShell) {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("stop_core");
        setRestartStatus(t("settings.startingCore"));
        const snapshot = await invoke<{ state: string }>("start_core");
        setLifecycle({ state: snapshot.state, core: snapshot.state });
        setRestartStatus(t("settings.waitingControllerServices"));
        const deadline = Date.now() + 30_000;
        while (Date.now() < deadline) {
          const current = await invoke<{ state: string; message?: string | null }>("lifecycle");
          setLifecycle({ state: current.state, core: current.state });
          if (current.state === "application_ready" || current.state === "core_ready") break;
          if (["core_start_failed", "core_timeout", "shutdown_timeout"].includes(current.state)) {
            throw new Error(current.message || `${t("settings.restartFailedState")} ${current.state}.`);
          }
          await new Promise((resolve) => window.setTimeout(resolve, 250));
        }
        const finalState = await invoke<{ state: string; message?: string | null }>("lifecycle");
        setLifecycle({ state: finalState.state, core: finalState.state });
        if (finalState.state !== "application_ready" && finalState.state !== "core_ready") {
          throw new Error(finalState.message || t("settings.coreReadyTimeout"));
        }
      } else {
        setRestartStatus(t("settings.restartingStatus"));
        setLifecycle(await api.restartCore());
      }
      setMessage(t("settings.coreRestarted"));
    } catch (reason) {
      setError(reason);
    } finally {
      setRestartBusy(false);
    }
  }

  async function startPairing() {
    setError(null);
    try {
      const challenge = await api.startPairing(origin.trim() || undefined);
      setPairing({ code: challenge.code, expires_at: challenge.expires_at });
      setRemote(await api.remoteStatus());
    } catch (reason) {
      setError(reason);
    }
  }

  async function disableRemote() {
    setError(null);
    try {
      setRemote(await api.disableRemote());
      setTunnel(await api.tunnelStatus());
      setPairing(null);
      setMessage(t("settings.remoteDisabled"));
    } catch (reason) {
      setError(reason);
    }
  }

  async function configureTunnel() {
    setTunnelBusy(true);
    setError(null);
    try {
      setTunnel(await api.configureTunnel(tunnelExecutable.trim() || null, tunnelConfigPath.trim() || null));
      setMessage(t("settings.tunnelValidated"));
    } catch (reason) {
      setError(reason);
    } finally {
      setTunnelBusy(false);
    }
  }

  async function startTunnel() {
    setTunnelBusy(true);
    setError(null);
    try {
      setTunnel(await api.startTunnel());
    } catch (reason) {
      setError(reason);
    } finally {
      setTunnelBusy(false);
    }
  }

  async function stopTunnel() {
    setTunnelBusy(true);
    setError(null);
    try {
      setTunnel(await api.stopTunnel());
    } catch (reason) {
      setError(reason);
    } finally {
      setTunnelBusy(false);
    }
  }

  async function checkForUpdate() {
    setUpdateBusy(true);
    setUpdateMessage(t("settings.checkingSignedUpdates"));
    setUpdateReady(false);
    let coreStopped = false;
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const candidate = await check();
      if (!candidate) {
        setUpdateMessage(t("settings.noSignedUpdate"));
        return;
      }
      const isTauriShell =
        window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost";
      const invoke = isTauriShell ? (await import("@tauri-apps/api/core")).invoke : null;
      if (invoke) {
        await invoke("stop_core");
        coreStopped = true;
      }
      let downloaded = 0;
      await candidate.downloadAndInstall((event) => {
        if (event.event === "Started") setUpdateMessage(t("settings.downloadingUpdate"));
        if (event.event === "Progress") {
          downloaded += event.data.chunkLength;
          setUpdateMessage(`${t("settings.downloadingUpdate")} ${downloaded} bytes`);
        }
        if (event.event === "Finished") setUpdateMessage(t("settings.installingUpdate"));
      });
      if (invoke) {
        setUpdateMessage(t("settings.updateInstalledRelaunching"));
        await (await import("@tauri-apps/plugin-process")).relaunch();
      } else {
        setUpdateReady(true);
        setUpdateMessage(t("settings.updateInstalledShell"));
      }
    } catch (reason) {
      try {
        if (coreStopped) await (await import("@tauri-apps/api/core")).invoke("start_core");
      } catch {
        // Preserve the original update error; diagnostics can expose a core
        // restart failure without masking the updater result.
      }
      // Update failure is deliberately non-destructive: the current install
      // remains usable and the user can retry or export diagnostics.
      setUpdateMessage(reason instanceof Error ? reason.message : t("settings.updateUnavailable"));
    } finally {
      setUpdateBusy(false);
    }
  }

  async function exportSupportBundle() {
    setError(null);
    try {
      const blob = await api.supportBundle();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "ds5forge-support-bundle.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage(t("settings.supportExported"));
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <>
      {restartBusy && (
        <div
          className="core-restart-backdrop"
          role="status"
          aria-live="polite"
          aria-label={t("settings.restartingAria")}
        >
          <div className="core-restart-status">
            <span className="spinner core-restart-spinner" aria-hidden="true" />
            <strong>{restartStatus}</strong>
            <span>{t("settings.restartOverlayBody")}</span>
          </div>
        </div>
      )}
      <PageHeader
        eyebrow={t("settings.eyebrow")}
        title={t("settings.title")}
        description={t("settings.description")}
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title={t("settings.coreUnavailableTitle")}>
          {t("settings.coreUnavailableBody")}
        </Notice>
      )}
      {message && (
        <Notice tone="success" title={t("settings.savedTitle")}>
          <Check size={14} />
          {message}
        </Notice>
      )}
      <ErrorText error={error} />
      <div className="stack">
        {draft ? (
          <Card>
            <div className="card-header">
              <div>
                <h2>{t("settings.appearance")}</h2>
                <p>{t("settings.appearanceHelp")}</p>
              </div>
              <Palette size={18} color="var(--accent)" />
            </div>
            <Field label={t("settings.theme")} help={t("settings.themeHelp")}>
              <Select
                aria-label={t("settings.theme")}
                value={draft.theme}
                disabled={coreStatus !== "online" || saving}
                onChange={(event) =>
                  setDraft((current) =>
                    current ? { ...current, theme: event.target.value as Config["theme"] } : current,
                  )
                }
              >
                {themes.map((item) => (
                  <option key={item} value={item}>
                    {themeLabel(item)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("settings.language")} help={t("settings.languageHelp")}>
              <Select
                aria-label={t("settings.language")}
                value={locale}
                onChange={(event) => setLocale(event.target.value as "en-US" | "pt-BR")}
              >
                <option value="en-US">{t("settings.english")}</option>
                <option value="pt-BR">{t("settings.portuguese")}</option>
              </Select>
            </Field>
          </Card>
        ) : (
          <Card>
            <div className="card-header">
              <div>
                <h2>{t("settings.corePreferences")}</h2>
                <p>{t("settings.corePreferencesHelp")}</p>
              </div>
              <Palette size={18} color="var(--accent)" />
            </div>
            {coreStatus === "online" ? (
              <LoadingState label={t("settings.waitingCorePreferences")} />
            ) : (
              <EmptyState
                title={t("settings.corePreferencesUnavailable")}
                description={t("settings.corePreferencesUnavailableBody")}
              />
            )}
          </Card>
        )}
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("settings.desktop")}</h2>
              <p>{t("settings.desktopHelp")}</p>
            </div>
            <Power size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>{t("settings.applicationVersion")}</dt>
              <dd>{appInfo?.version ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.shellPlatform")}</dt>
              <dd>{appInfo?.platform ?? t("settings.browserUnknown")}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.lifecycle")}</dt>
              <dd>{lifecycle?.state ?? "—"}</dd>
            </div>
          </dl>
          <div className="form-actions">
            <span className="muted">{t("settings.restartHelp")}</span>
            <Button variant="quiet" onClick={() => void restartCore()} disabled={restartBusy}>
              <RefreshCw size={15} /> {restartBusy ? t("settings.restarting") : t("settings.restartCore")}
            </Button>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("settings.startup")}</h2>
              <p>{t("settings.startupHelp")}</p>
            </div>
            <Power size={18} color="var(--violet)" />
          </div>
          <label className="toggle-row">
            <span>
              <span className="toggle-label">{t("settings.launchAtSignIn")}</span>
              <span className="toggle-description">{t("settings.autostartIntegration")}</span>
            </span>
            <input
              aria-label={t("settings.launchAtSignIn")}
              type="checkbox"
              checked={autostart}
              disabled={!autostartSupported}
              onChange={(event) => void toggleAutostart(event.target.checked)}
            />
            <span className="toggle-control" aria-hidden="true">
              <span />
            </span>
          </label>
          {!autostartSupported && <p className="muted">{t("settings.autostartShellOnly")}</p>}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("settings.updates")}</h2>
              <p>{t("settings.updatesHelp")}</p>
            </div>
            <Download size={18} color="var(--success)" />
          </div>
          <div className="form-actions">
            <span className="muted">{t("settings.updateProgressHelp")}</span>
            <Button onClick={() => void checkForUpdate()} disabled={updateBusy}>
              <Download size={15} /> {updateBusy ? t("settings.checking") : t("settings.checkForUpdates")}
            </Button>
          </div>
          {updateMessage && (
            <Notice tone="info" title={t("settings.updater")}>
              {updateMessage}
            </Notice>
          )}
          {updateReady && (
            <Button
              variant="quiet"
              onClick={() =>
                void import("@tauri-apps/plugin-process")
                  .then(({ relaunch }) => relaunch())
                  .catch((reason) => setError(reason))
              }
            >
              {t("settings.restartToApply")}
            </Button>
          )}
        </Card>
        <details className="settings-advanced">
          <summary>{t("settings.advancedRemote")}</summary>
          <Card>
            <div className="card-header">
              <div>
                <h2>{t("settings.remoteAccess")}</h2>
                <p>{t("settings.remoteAccessHelp")}</p>
              </div>
              <KeyRound size={18} color="var(--warning)" />
            </div>
            <Field label={t("settings.registeredOrigin")} help={t("settings.registeredOriginHelp")}>
              <input
                className="input"
                aria-label={t("settings.registeredOrigin")}
                value={origin}
                onChange={(event) => setOrigin(event.target.value)}
                placeholder="https://remote.example"
              />
            </Field>
            <div className="form-actions">
              <span className="muted">
                {t("settings.status")}: {remote?.status ?? t("settings.off")} · {remote?.sessions.length ?? 0}{" "}
                {t("settings.sessions")}
              </span>
              <div className="button-group">
                <Button
                  variant="quiet"
                  onClick={() => void startPairing()}
                  disabled={coreStatus !== "online"}
                >
                  {t("settings.startPairing")}
                </Button>
                <Button variant="danger" onClick={() => void disableRemote()} disabled={!remote?.enabled}>
                  {t("settings.disableRemote")}
                </Button>
              </div>
            </div>
            {pairing && (
              <Notice tone="warning" title={t("settings.pairingCode")}>
                {pairing.code} · {t("settings.expires")}{" "}
                {new Date(pairing.expires_at * 1000).toLocaleTimeString()}
              </Notice>
            )}
            {remote?.sessions.map((session) => (
              <div className="subsystem" key={session.session_id}>
                <span>
                  {session.origin} ·{" "}
                  {session.expired || session.revoked ? t("settings.inactive") : t("settings.active")}
                </span>
                <Button
                  variant="quiet"
                  onClick={() =>
                    void api.revokeRemote(session.session_id).then(() => api.remoteStatus().then(setRemote))
                  }
                >
                  {t("settings.revoke")}
                </Button>
              </div>
            ))}
            <div className="subsystem-list" style={{ marginTop: 16 }}>
              <div className="subsystem">
                <span>
                  Cloudflared
                  <small>{tunnel?.message ?? t("settings.tunnelDefaultMessage")}</small>
                </span>
                <span className={tunnel?.status === "online" ? "good" : "muted"}>
                  {tunnel?.status ?? t("settings.off")}
                </span>
              </div>
            </div>
            <div className="stack" style={{ marginTop: 16 }}>
              <Field label={t("settings.tunnelExecutable")} help={t("settings.tunnelExecutableHelp")}>
                <input
                  className="input"
                  aria-label={t("settings.tunnelExecutable")}
                  value={tunnelExecutable}
                  onChange={(event) => setTunnelExecutable(event.target.value)}
                  placeholder="cloudflared"
                />
              </Field>
              <Field label={t("settings.tunnelYaml")} help={t("settings.tunnelYamlHelp")}>
                <input
                  className="input"
                  aria-label={t("settings.tunnelYaml")}
                  value={tunnelConfigPath}
                  onChange={(event) => setTunnelConfigPath(event.target.value)}
                  placeholder="C:\\Users\\you\\.cloudflared\\config.yml"
                />
              </Field>
              <div className="button-group">
                <Button
                  variant="quiet"
                  onClick={() => void configureTunnel()}
                  disabled={tunnelBusy || coreStatus !== "online"}
                >
                  {t("settings.validateTunnel")}
                </Button>
                <Button onClick={() => void startTunnel()} disabled={tunnelBusy || !remote?.enabled}>
                  {t("settings.startTunnel")}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => void stopTunnel()}
                  disabled={tunnelBusy || coreStatus !== "online"}
                >
                  {t("settings.stopTunnel")}
                </Button>
              </div>
            </div>
          </Card>
        </details>
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("settings.advanced")}</h2>
              <p>{t("settings.advancedHelp")}</p>
            </div>
            <ShieldCheck size={18} color="var(--success)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>{t("settings.apiEndpoint")}</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.transport")}</dt>
              <dd>{t("settings.usbWiredOnly")}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.virtualController")}</dt>
              <dd>{t("settings.virtualUnavailable")}</dd>
            </div>
          </dl>
          <Button
            variant="quiet"
            onClick={() => void exportSupportBundle()}
            disabled={coreStatus !== "online"}
          >
            <Download size={15} /> {t("settings.exportSupport")}
          </Button>
        </Card>
        {draft && (
          <Card>
            <div className="card-header">
              <div>
                <h2>{t("settings.micButton")}</h2>
                <p>{t("settings.micButtonHelp")}</p>
              </div>
              <MonitorCog size={18} color="var(--violet)" />
            </div>
            <Field label={t("settings.buttonAction")} help={micHelp(draft.mic_button)}>
              <Select
                aria-label={t("settings.micButton")}
                value={draft.mic_button}
                disabled={coreStatus !== "online" || saving}
                onChange={(event) =>
                  setDraft((current) =>
                    current
                      ? { ...current, mic_button: event.target.value as Config["mic_button"] }
                      : current,
                  )
                }
              >
                {micBehaviors.map((item) => (
                  <option key={item} value={item}>
                    {micLabel(item)}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="form-actions">
              <span className="muted">{dirty ? t("settings.unsaved") : t("settings.upToDate")}</span>
              <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
                <Save size={15} />
                {saving ? t("settings.saving") : t("settings.saveSettings")}
              </Button>
            </div>
          </Card>
        )}
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("settings.localService")}</h2>
              <p>{t("settings.localServiceHelp")}</p>
            </div>
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>{t("settings.apiEndpoint")}</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.transportScope")}</dt>
              <dd>{t("settings.usbWiredOnly")}</dd>
            </div>
            <div className="data-item">
              <dt>{t("settings.coreStart")}</dt>
              <dd>{t("settings.coreStartManaged")}</dd>
            </div>
          </dl>
        </Card>
      </div>
    </>
  );
}
