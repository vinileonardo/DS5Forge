import { Activity, AlertTriangle, Cable, CircleCheck, Radio, RefreshCw, Server, Volume2 } from "lucide-react";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";
import { API_BASE_URL } from "../../lib/api/client";
import { Button, Card, EmptyState, Notice, PageHeader, StatusPill } from "../../components/ui";

function tone(value: string): "success" | "warning" | "danger" | "neutral" {
  if (["healthy", "ready", "connected", "listening", "online"].includes(value)) return "success";
  if (["degraded", "waiting", "waiting_for_controller", "reconnecting", "starting"].includes(value))
    return "warning";
  if (["error", "stopped", "offline"].includes(value)) return "danger";
  return "neutral";
}

function time(value: number): string {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function DiagnosticsPage() {
  const {
    coreStatus,
    runtime,
    health,
    stale,
    events,
    clientErrors,
    lastReconnectAt,
    reconnectAttempt,
    refresh,
  } = useRuntime();
  const subsystems = runtime?.health.subsystems ?? health?.subsystems ?? {};
  const lastError = runtime?.last_error;

  return (
    <>
      <PageHeader
        eyebrow="Local service visibility"
        title="Diagnostics"
        description="Separate frontend reachability, Python core health, USB controller lifecycle and audio subsystem state."
        action={
          <Button variant="quiet" onClick={() => void refresh()}>
            <RefreshCw size={15} />
            Refresh HTTP
          </Button>
        }
      />
      {coreStatus === "protocol_error" && (
        <Notice tone="danger" title="Protocol error">
          A known payload could not be validated. The client stopped trusting realtime state and recorded the
          detail below.
        </Notice>
      )}
      <div className="diagnostic-grid">
        <Card>
          <div className="card-header">
            <div>
              <h2>Core</h2>
              <p>Transport and API boundary.</p>
            </div>
            <Server size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Reachability</dt>
              <dd className={coreStatus === "online" ? "good" : "warn"}>{coreStatus}</dd>
            </div>
            <div className="data-item">
              <dt>HTTP endpoint</dt>
              <dd>{API_BASE_URL}</dd>
            </div>
            <div className="data-item">
              <dt>WebSocket</dt>
              <dd className={coreStatus === "online" ? "good" : "warn"}>
                {coreStatus}
                {reconnectAttempt ? ` · attempt ${reconnectAttempt}` : ""}
              </dd>
            </div>
            <div className="data-item">
              <dt>Last reconnect</dt>
              <dd>{lastReconnectAt ? time(lastReconnectAt) : "This session has not reconnected"}</dd>
            </div>
            <div className="data-item">
              <dt>Process alive</dt>
              <dd className={health?.process_alive ? "good" : "bad"}>
                {health ? String(health.process_alive) : "unknown"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Controller</h2>
              <p>Snapshot from the Python authority.</p>
            </div>
            <Cable size={18} color="var(--violet)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Lifecycle</dt>
              <dd className={stale ? "warn" : tone(runtime?.connection ?? "unknown")}>
                {stale ? `stale · ${runtime?.connection ?? "unknown"}` : (runtime?.connection ?? "unknown")}
              </dd>
            </div>
            <div className="data-item">
              <dt>Identity</dt>
              <dd>{runtime?.identity?.model ?? "Unavailable"}</dd>
            </div>
            <div className="data-item">
              <dt>Transport</dt>
              <dd>{runtime?.identity?.transport ?? "Unavailable"}</dd>
            </div>
            <div className="data-item">
              <dt>State sequence</dt>
              <dd>{runtime?.sequence ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>Snapshot time</dt>
              <dd>{runtime ? time(runtime.updated_at * 1000) : "—"}</dd>
            </div>
          </dl>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Subsystems</h2>
              <p>Health values are not inferred by the frontend.</p>
            </div>
            <Activity size={18} color="var(--success)" />
          </div>
          <div className="subsystem-list">
            {Object.keys(subsystems).length ? (
              Object.entries(subsystems).map(([name, value]) => (
                <div className="subsystem" key={name}>
                  <span>{name}</span>
                  <StatusPill tone={tone(value)} label={value} />
                </div>
              ))
            ) : (
              <EmptyState
                title="No health data"
                description="The local core has not returned a health snapshot."
              />
            )}
          </div>
          {health?.degraded.length ? (
            <div className="notice notice-warning" style={{ marginTop: 16, marginBottom: 0 }}>
              <strong>Degraded:</strong>
              <span>{health.degraded.join(", ")}</span>
            </div>
          ) : (
            <div className="notice notice-success" style={{ marginTop: 16, marginBottom: 0 }}>
              <CircleCheck size={14} />
              <span>No degraded subsystem reported.</span>
            </div>
          )}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Audio capture</h2>
              <p>WASAPI loopback state exposed by P0.</p>
            </div>
            <Volume2 size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Status</dt>
              <dd className={tone(runtime?.audio.status ?? "unknown")}>
                {runtime?.audio.status ?? "Unavailable"}
              </dd>
            </div>
            <div className="data-item">
              <dt>Device</dt>
              <dd>{runtime?.audio.device ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>Audio error</dt>
              <dd className={runtime?.audio.error ? "bad" : "good"}>{runtime?.audio.error ?? "None"}</dd>
            </div>
          </dl>
        </Card>
      </div>
      <div className="stack" style={{ marginTop: 18 }}>
        <Card>
          <div className="card-header">
            <div>
              <h2>Errors</h2>
              <p>Safe structured errors from the core and client protocol validation.</p>
            </div>
            <AlertTriangle size={18} color="var(--warning)" />
          </div>
          {lastError ? (
            <div className="error-box">
              <strong>
                {lastError.code} · {lastError.recoverable ? "recoverable" : "not recoverable"}
              </strong>
              <p>{lastError.message}</p>
              {lastError.detail && <p>{lastError.detail}</p>}
            </div>
          ) : (
            <p className="muted">The core has not reported a runtime error.</p>
          )}
          {clientErrors.length > 0 && (
            <div className="stack" style={{ marginTop: 12 }}>
              {clientErrors.map((error, index) => (
                <div className="notice notice-danger" key={`${error}-${index}`}>
                  <Radio size={14} />
                  <span>{error}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Session timeline</h2>
              <p>Bounded in-memory events from this browser session.</p>
            </div>
          </div>
          {events.length ? (
            <div className="timeline">
              {events.map((event) => (
                <div className="timeline-item" key={event.id}>
                  <div>
                    <p className="timeline-summary">
                      {event.summary}
                      <span className="timeline-time">{time(event.at)}</span>
                    </p>
                    {event.detail && <div className="timeline-detail">{event.detail}</div>}
                    <div className="timeline-detail">{event.kind}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No WebSocket events received yet.</p>
          )}
        </Card>
      </div>
    </>
  );
}
