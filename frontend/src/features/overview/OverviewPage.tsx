import { BatteryMedium, Cable, CheckCircle2, Cpu, ShieldAlert, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";

import {
  Card,
  EmptyState,
  ErrorText,
  LoadingState,
  Notice,
  PageHeader,
  StatusPill,
  Toggle,
} from "../../components/ui";
import { controllerLabel, useRuntime } from "../../lib/runtime/RuntimeProvider";

function connectionTone(connection: string | undefined): "success" | "warning" | "danger" | "neutral" {
  if (connection === "connected") return "success";
  if (connection === "error") return "danger";
  if (connection === "connecting" || connection === "reconnecting") return "warning";
  return "neutral";
}

export function OverviewPage() {
  const { runtime, health, coreStatus, stale, loading, canControl, setRumble, setTouchpad } = useRuntime();
  const [pending, setPending] = useState<"rumble" | "touchpad" | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const current = runtime && !stale ? runtime : null;

  async function toggle(target: "rumble" | "touchpad", enabled: boolean) {
    setPending(target);
    setActionError(null);
    try {
      if (target === "rumble") await setRumble(enabled);
      else await setTouchpad(enabled);
    } catch (error) {
      setActionError(error);
    } finally {
      setPending(null);
    }
  }

  if (loading && !runtime) return <LoadingState />;

  return (
    <>
      <PageHeader
        eyebrow="Control center"
        title="Overview"
        description="See whether the local core and your wired DualSense are healthy, connected and configured as expected."
      />
      {coreStatus !== "online" && (
        <Notice
          tone={coreStatus === "protocol_error" ? "danger" : "warning"}
          title={coreStatus === "protocol_error" ? "State cannot be trusted" : "Local core offline"}
        >
          The browser will retry automatically. Configuration is never fabricated while the core is
          unavailable.
        </Notice>
      )}
      <ErrorText error={actionError} />
      <div className="overview-grid">
        <Card className="hero-card">
          <div className="hero-kicker">
            <span>Controller status</span>
            <StatusPill
              tone={connectionTone(current?.connection)}
              label={current ? current.connection : stale && runtime ? "stale" : "waiting"}
            />
          </div>
          <div className="hero-state">
            <div className="hero-state-mark">
              <Cable size={22} />
            </div>
            <div>
              <h2>{current?.identity?.model ?? "Wired DualSense"}</h2>
              <p>
                {current
                  ? `${current.identity?.transport.toUpperCase() ?? "USB"} transport · ${current.identity?.serial ?? "Identity available from core"}`
                  : controllerLabel(runtime, stale)}
              </p>
            </div>
          </div>
          <div className="metric-row">
            <div className="metric">
              <span className="metric-label">
                <BatteryMedium size={12} /> Battery
              </span>
              <strong className="metric-value">{current ? `${current.battery.level}%` : "—"}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Charging</span>
              <strong className="metric-value">
                {current?.battery.charging === true
                  ? "Yes"
                  : current?.battery.charging === false
                    ? "No"
                    : "Unknown"}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Profile</span>
              <strong className="metric-value">{current?.active_profile ?? "—"}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Audio</span>
              <strong className="metric-value">{current?.audio.status ?? "—"}</strong>
            </div>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Quick controls</h2>
              <p>Only actions supported by the current P0 core.</p>
            </div>
            <Sparkles size={17} color="var(--accent)" />
          </div>
          <div className="quick-actions">
            <Toggle
              label="Haptics"
              description={
                canControl ? "Audio-driven rumble output" : "Requires an online connected controller"
              }
              checked={current?.rumble_enabled ?? false}
              disabled={!canControl || pending !== null}
              onChange={(value) => void toggle("rumble", value)}
            />
            <Toggle
              label="Touchpad"
              description={
                canControl ? "Mouse and gesture output" : "Requires an online connected controller"
              }
              checked={current?.touchpad_enabled ?? false}
              disabled={!canControl || pending !== null}
              onChange={(value) => void toggle("touchpad", value)}
            />
          </div>
          <div className="form-actions">
            <Link className="button button-quiet" to="/haptics">
              Tune haptics
            </Link>
            <Link className="button button-quiet" to="/touchpad">
              Touchpad settings
            </Link>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Runtime summary</h2>
              <p>Reported by the Python core.</p>
            </div>
            <Cpu size={17} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Core health</dt>
              <dd className={health?.status === "healthy" ? "good" : "warn"}>
                {health?.status ?? "Unavailable"}
              </dd>
            </div>
            <div className="data-item">
              <dt>Audio device</dt>
              <dd>{current?.audio.device ?? "Not active"}</dd>
            </div>
            <div className="data-item">
              <dt>Capabilities</dt>
              <dd>
                {current ? `${Object.values(current.capabilities).filter(Boolean).length} available` : "—"}
              </dd>
            </div>
            <div className="data-item">
              <dt>Last update</dt>
              <dd>{current ? new Date(current.updated_at * 1000).toLocaleTimeString() : "—"}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Health and errors</h2>
              <p>Issues stay visible until the core reports recovery.</p>
            </div>
            <ShieldAlert size={17} color="var(--warning)" />
          </div>
          {current?.last_error ? (
            <div className="error-box">
              <strong>{current.last_error.code}</strong>
              <p>{current.last_error.message}</p>
              <p>{current.last_error.recoverable ? "Recoverable" : "Requires attention"}</p>
            </div>
          ) : health?.degraded.length ? (
            <div className="stack">
              {health.degraded.map((item) => (
                <StatusPill key={item} tone="warning" label={item} />
              ))}
            </div>
          ) : (
            <div className="empty-state" style={{ minHeight: 120 }}>
              <CheckCircle2 color="var(--success)" size={25} />
              <p>No degraded subsystems reported.</p>
            </div>
          )}
          <div className="form-actions">
            <Link className="button-link" to="/diagnostics">
              Open diagnostics →
            </Link>
          </div>
        </Card>
      </div>
      {runtime?.identity && runtime.identity.transport !== "usb" && (
        <Notice tone="danger" title="Unsupported transport">
          The core reported a non-USB transport. P1 is intentionally wired-only.
        </Notice>
      )}
      {runtime?.capabilities && !runtime.capabilities.rumble && (
        <Notice tone="warning" title="Haptics unavailable">
          This controller does not expose rumble capability to the core.
        </Notice>
      )}
      {!runtime && coreStatus === "online" && (
        <EmptyState
          title="Waiting for controller"
          description="Connect a DualSense with a USB cable. The core will update this view when the controller appears."
        />
      )}
      <span className="sr-only">{pending ? `${pending} update pending` : ""}</span>
    </>
  );
}
