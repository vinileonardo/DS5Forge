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
import { useRuntime } from "../../lib/runtime/RuntimeProvider";

const themes: Config["theme"][] = ["Dark", "Light", "Liquid Glass"];
const micBehaviors: Array<{ value: Config["mic_button"]; label: string; help: string }> = [
  { value: "master", label: "Master behavior", help: "Toggle the master behavior defined by the core." },
  { value: "rumble", label: "Haptics", help: "Toggle audio-driven rumble from the controller button." },
  {
    value: "trackpad",
    label: "Touchpad",
    help: "Toggle touchpad mouse behavior from the controller button.",
  },
];

type SettingsDraft = Pick<Config, "theme" | "mic_button">;

export function SettingsPage() {
  const { config, coreStatus, updateConfig } = useRuntime();
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

  const dirty = Boolean(
    config && draft && (config.theme !== draft.theme || config.mic_button !== draft.mic_button),
  );

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
      if (!draft) throw new Error("Core settings are unavailable.");
      const saved = await updateConfig({
        theme: draft.theme,
        mic_button: draft.mic_button,
      });
      setDraft({ theme: saved.theme, mic_button: saved.mic_button });
      setMessage("Settings saved.");
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
      setMessage(enabled ? "Autostart enabled." : "Autostart disabled.");
    } catch (reason) {
      setError(reason);
    }
  }

  async function restartCore() {
    setError(null);
    try {
      const isTauriShell =
        window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost";
      if (isTauriShell) {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("stop_core");
        const snapshot = await invoke<{ state: string }>("start_core");
        setLifecycle({ state: snapshot.state, core: snapshot.state });
      } else {
        setLifecycle(await api.restartCore());
      }
      setMessage("Core restart requested. Hardware outputs are released by the core before restart.");
    } catch (reason) {
      setError(reason);
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
      setMessage("Remote access disabled; sessions and tunnel state were closed.");
    } catch (reason) {
      setError(reason);
    }
  }

  async function configureTunnel() {
    setTunnelBusy(true);
    setError(null);
    try {
      setTunnel(await api.configureTunnel(tunnelExecutable.trim() || null, tunnelConfigPath.trim() || null));
      setMessage("Cloudflared configuration validated. It remains stopped until explicitly started.");
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
    setUpdateMessage(null);
    setUpdateReady(false);
    let coreStopped = false;
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const candidate = await check();
      if (!candidate) {
        setUpdateMessage("No signed update is available.");
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
        if (event.event === "Started") setUpdateMessage("Downloading signed update…");
        if (event.event === "Progress") {
          downloaded += event.data.chunkLength;
          setUpdateMessage(`Downloading signed update… ${downloaded} bytes`);
        }
        if (event.event === "Finished") {
          setUpdateReady(true);
          setUpdateMessage("Update installed. Restart DS5Forge to apply it.");
        }
      });
    } catch (reason) {
      try {
        if (coreStopped) await (await import("@tauri-apps/api/core")).invoke("start_core");
      } catch {
        // Preserve the original update error; diagnostics can expose a core
        // restart failure without masking the updater result.
      }
      // Update failure is deliberately non-destructive: the current install
      // remains usable and the user can retry or export diagnostics.
      setUpdateMessage(reason instanceof Error ? reason.message : "Update check unavailable in this shell.");
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
      setMessage("Support Bundle exported with secrets and sensitive paths redacted.");
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Client and core preferences"
        title="Settings"
        description="Keep the existing schema-v1 preferences visible without introducing a second local configuration system."
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title="Core unavailable">
          Core-backed preferences are unavailable, but desktop recovery controls and signed updates remain
          available.
        </Notice>
      )}
      {message && (
        <Notice tone="success" title="Saved">
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
                <h2>Appearance</h2>
                <p>
                  The existing persisted theme remains authoritative. Dark is the P1 default only when no
                  saved value exists.
                </p>
              </div>
              <Palette size={18} color="var(--accent)" />
            </div>
            <Field
              label="Theme"
              help="Liquid Glass remains available when it is present in the core contract."
            >
              <Select
                aria-label="Theme"
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
                    {item}
                  </option>
                ))}
              </Select>
            </Field>
          </Card>
        ) : (
          <Card>
            <div className="card-header">
              <div>
                <h2>Core preferences</h2>
                <p>Theme and controller-button preferences are persisted by the local core.</p>
              </div>
              <Palette size={18} color="var(--accent)" />
            </div>
            {coreStatus === "online" ? (
              <LoadingState label="Waiting for persisted settings from the local core…" />
            ) : (
              <EmptyState
                title="Core preferences unavailable"
                description="Desktop recovery, startup and signed update controls remain available below."
              />
            )}
          </Card>
        )}
        <Card>
          <div className="card-header">
            <div>
              <h2>Desktop</h2>
              <p>
                The Tauri shell owns the Python sidecar, tray, single-instance behavior and coordinated
                teardown.
              </p>
            </div>
            <Power size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Application version</dt>
              <dd>{appInfo?.version ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>Shell platform</dt>
              <dd>{appInfo?.platform ?? "Browser / unknown"}</dd>
            </div>
            <div className="data-item">
              <dt>Lifecycle</dt>
              <dd>{lifecycle?.state ?? "—"}</dd>
            </div>
          </dl>
          <div className="form-actions">
            <span className="muted">Restart releases controller outputs before starting the core again.</span>
            <Button variant="quiet" onClick={() => void restartCore()}>
              <RefreshCw size={15} /> Restart core
            </Button>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Startup</h2>
              <p>Autostart is disabled by default and can be reversed at any time.</p>
            </div>
            <Power size={18} color="var(--violet)" />
          </div>
          <label className="toggle-row">
            <span>
              <span className="toggle-label">Launch at Windows sign-in</span>
              <span className="toggle-description">Uses the official Tauri autostart integration.</span>
            </span>
            <input
              aria-label="Launch at Windows sign-in"
              type="checkbox"
              checked={autostart}
              disabled={!autostartSupported}
              onChange={(event) => void toggleAutostart(event.target.checked)}
            />
            <span className="toggle-control" aria-hidden="true">
              <span />
            </span>
          </label>
          {!autostartSupported && (
            <p className="muted">
              Available in the installed desktop shell; browser preview cannot modify Windows startup.
            </p>
          )}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Updates</h2>
              <p>
                Only HTTPS metadata with a detached Tauri signature is accepted. Failed updates leave the
                current install intact.
              </p>
            </div>
            <Download size={18} color="var(--success)" />
          </div>
          <div className="form-actions">
            <span className="muted">Windows installer updates use passive progress feedback.</span>
            <Button onClick={() => void checkForUpdate()} disabled={updateBusy}>
              <Download size={15} /> {updateBusy ? "Checking…" : "Check for updates"}
            </Button>
          </div>
          {updateMessage && (
            <Notice tone="info" title="Updater">
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
              Restart to apply
            </Button>
          )}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Remote Access</h2>
              <p>
                OFF by default. Pairing starts locally, stores only session hashes, and authenticates remote
                HTTP/WebSocket with a Secure HttpOnly cookie.
              </p>
            </div>
            <KeyRound size={18} color="var(--warning)" />
          </div>
          <Field
            label="Registered HTTPS origin"
            help="Use the exact HTTPS origin served by the remote access gateway; no path, query or wildcard."
          >
            <input
              className="input"
              aria-label="Registered HTTPS origin"
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
              placeholder="https://remote.example"
            />
          </Field>
          <div className="form-actions">
            <span className="muted">
              Status: {remote?.status ?? "off"} · {remote?.sessions.length ?? 0} session(s)
            </span>
            <div className="button-group">
              <Button variant="quiet" onClick={() => void startPairing()} disabled={coreStatus !== "online"}>
                Start one-time pairing
              </Button>
              <Button variant="danger" onClick={() => void disableRemote()} disabled={!remote?.enabled}>
                Disable remote
              </Button>
            </div>
          </div>
          {pairing && (
            <Notice tone="warning" title="One-time pairing code">
              {pairing.code} · expires {new Date(pairing.expires_at * 1000).toLocaleTimeString()}
            </Notice>
          )}
          {remote?.sessions.map((session) => (
            <div className="subsystem" key={session.session_id}>
              <span>
                {session.origin} · {session.expired || session.revoked ? "inactive" : "active"}
              </span>
              <Button
                variant="quiet"
                onClick={() =>
                  void api.revokeRemote(session.session_id).then(() => api.remoteStatus().then(setRemote))
                }
              >
                Revoke
              </Button>
            </div>
          ))}
          <div className="subsystem-list" style={{ marginTop: 16 }}>
            <div className="subsystem">
              <span>
                Cloudflared
                <small>
                  {tunnel?.message ?? "Explicit configuration only; no download or silent install."}
                </small>
              </span>
              <span className={tunnel?.status === "online" ? "good" : "muted"}>
                {tunnel?.status ?? "off"}
              </span>
            </div>
          </div>
          <div className="stack" style={{ marginTop: 16 }}>
            <Field
              label="Cloudflared executable"
              help="Optional absolute executable path or a user-managed PATH entry. DS5Forge never downloads it."
            >
              <input
                className="input"
                aria-label="Cloudflared executable"
                value={tunnelExecutable}
                onChange={(event) => setTunnelExecutable(event.target.value)}
                placeholder="cloudflared"
              />
            </Field>
            <Field
              label="Cloudflared YAML config"
              help="Absolute YAML path; raw tunnel tokens are rejected and the file is never exported."
            >
              <input
                className="input"
                aria-label="Cloudflared YAML config"
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
                Validate tunnel config
              </Button>
              <Button onClick={() => void startTunnel()} disabled={tunnelBusy || !remote?.enabled}>
                Start tunnel
              </Button>
              <Button
                variant="danger"
                onClick={() => void stopTunnel()}
                disabled={tunnelBusy || coreStatus !== "online"}
              >
                Stop tunnel
              </Button>
            </div>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Advanced</h2>
              <p>Diagnostics exports are bounded and sanitized for support review.</p>
            </div>
            <ShieldCheck size={18} color="var(--success)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>API endpoint</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>Transport</dt>
              <dd>USB / wired only</dd>
            </div>
            <div className="data-item">
              <dt>Virtual controller</dt>
              <dd>Unavailable by decision; no driver is installed</dd>
            </div>
          </dl>
          <Button
            variant="quiet"
            onClick={() => void exportSupportBundle()}
            disabled={coreStatus !== "online"}
          >
            <Download size={15} /> Export Support Bundle
          </Button>
        </Card>
        {draft && (
          <Card>
            <div className="card-header">
              <div>
                <h2>Microphone button behavior</h2>
                <p>These labels map directly to the current `master`, `rumble` and `trackpad` wire values.</p>
              </div>
              <MonitorCog size={18} color="var(--violet)" />
            </div>
            <Field
              label="Button action"
              help={micBehaviors.find((item) => item.value === draft.mic_button)?.help}
            >
              <Select
                aria-label="Microphone button behavior"
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
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="form-actions">
              <span className="muted">{dirty ? "Unsaved settings" : "Settings are up to date."}</span>
              <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
                <Save size={15} />
                {saving ? "Saving…" : "Save settings"}
              </Button>
            </div>
          </Card>
        )}
        <Card>
          <div className="card-header">
            <div>
              <h2>Local service</h2>
              <p>Informational only. P1 does not expose an arbitrary endpoint editor.</p>
            </div>
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>API endpoint</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>Transport scope</dt>
              <dd>USB / wired only</dd>
            </div>
            <div className="data-item">
              <dt>Core start</dt>
              <dd>Installed desktop shell manages the packaged core automatically.</dd>
            </div>
          </dl>
        </Card>
      </div>
    </>
  );
}
