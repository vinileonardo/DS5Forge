import { AudioWaveform, RotateCcw, Save, TimerReset } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Card,
  EmptyState,
  ErrorText,
  Field,
  LoadingState,
  Notice,
  NumberInput,
  PageHeader,
  StatusPill,
  Toggle,
} from "../../components/ui";
import { RUMBLE_FIELD_SPECS, type RumbleConfig } from "../../lib/api/contracts";
import { ApiError, errorMessage, fieldErrorMap } from "../../lib/api/errors";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";
import { capabilityEnabled, capabilityReason } from "../controller/visualizers";

const groupOrder = [
  "Frequency response",
  "Envelope",
  "Detection and gating",
  "Transient shaping",
  "Output shaping",
];

function groupFields() {
  return groupOrder.map((group) => ({
    group,
    fields: RUMBLE_FIELD_SPECS.filter((field) => field.group === group),
  }));
}

export function HapticsPage() {
  const {
    config,
    runtime,
    coreStatus,
    stale,
    canControl,
    updateConfig,
    setRumble,
    testRumble,
    startHapticsTest,
    cancelHapticsTest,
  } = useRuntime();
  const [draft, setDraft] = useState<RumbleConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingToggle, setPendingToggle] = useState(false);
  const [testing, setTesting] = useState(false);
  const [benchPending, setBenchPending] = useState<"start" | "cancel" | null>(null);
  const [benchDraft, setBenchDraft] = useState({ left: 200, right: 160, duration_ms: 350 });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const dirty = useMemo(
    () => Boolean(config && draft && JSON.stringify(config.rumble) !== JSON.stringify(draft)),
    [config, draft],
  );

  useEffect(() => {
    if (config && !dirty) setDraft(config.rumble);
  }, [config, dirty]);

  const grouped = useMemo(groupFields, []);
  const rumbleAvailable = capabilityEnabled(runtime, "rumble");

  if (!config || !draft) {
    return coreStatus === "online" ? (
      <LoadingState label="Waiting for haptics configuration from the local core…" />
    ) : (
      <>
        <PageHeader
          eyebrow="Audio-driven output"
          title="Haptics"
          description="Tune the existing P0 audio-to-rumble mapping."
        />
        <EmptyState
          title="Haptics configuration unavailable"
          description="Start the local core to load persisted haptics values. The browser will retry without creating defaults."
        />
      </>
    );
  }
  const currentDraft = draft;

  function change(key: keyof RumbleConfig, value: string) {
    setMessage(null);
    setFieldErrors((current) => ({ ...current, [key]: "" }));
    setDraft((current) => (current ? { ...current, [key]: Number(value) } : current));
  }

  async function save() {
    setSaving(true);
    setError(null);
    setMessage(null);
    setFieldErrors({});
    try {
      const saved = await updateConfig({ rumble: currentDraft });
      setDraft(saved.rumble);
      setMessage("Haptics configuration saved.");
    } catch (reason) {
      setError(reason);
      if (reason instanceof ApiError) setFieldErrors(fieldErrorMap(reason));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(enabled: boolean) {
    setPendingToggle(true);
    setError(null);
    setMessage(null);
    try {
      await setRumble(enabled);
      setMessage(enabled ? "Haptics enabled." : "Haptics disabled and motors neutralized.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPendingToggle(false);
    }
  }

  async function test() {
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      const accepted = await testRumble({ duration_ms: 350 });
      setMessage(
        accepted
          ? "Bounded rumble test accepted; it will stop automatically."
          : "The core did not accept the test because no controller is available.",
      );
    } catch (reason) {
      setError(reason);
    } finally {
      setTesting(false);
    }
  }

  async function startBench() {
    setBenchPending("start");
    setError(null);
    setMessage(null);
    try {
      await startHapticsTest(benchDraft);
      setMessage("Bounded haptics test started; the server will neutralize the motors automatically.");
    } catch (reason) {
      setError(reason);
    } finally {
      setBenchPending(null);
    }
  }

  async function cancelBench() {
    setBenchPending("cancel");
    setError(null);
    try {
      await cancelHapticsTest();
      setMessage("Haptics test cancelled and motors neutralized.");
    } catch (reason) {
      setError(reason);
    } finally {
      setBenchPending(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Audio-driven output"
        title="Haptics"
        description="Tune the existing P0 audio-to-rumble mapping. Values are validated again by the Python core before reaching the controller."
        action={
          <Button variant="quiet" onClick={() => setDraft(config.rumble)} disabled={!dirty || saving}>
            <RotateCcw size={15} />
            Reset draft
          </Button>
        }
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title="Core unavailable">
          Saved values are not editable until the local core responds.
        </Notice>
      )}
      {runtime && !rumbleAvailable && (
        <Notice tone="warning" title="Rumble capability unavailable">
          {capabilityReason(runtime, "rumble")}
        </Notice>
      )}
      {message && (
        <Notice tone="success" title="Done">
          {message}
        </Notice>
      )}
      <ErrorText error={error} />
      {error instanceof ApiError && Object.keys(fieldErrors).length > 0 && (
        <Notice tone="danger" title="Validation needs attention">
          The core rejected one or more fields. Correct the highlighted values and save again.
        </Notice>
      )}
      <div className="stack">
        <Card>
          <div className="card-header">
            <div>
              <h2>Primary controls</h2>
              <p>Changes are applied only after server confirmation.</p>
            </div>
            <AudioWaveform size={18} color="var(--accent)" />
          </div>
          <Toggle
            label="Master haptics"
            description="Enable audio-driven rumble output."
            checked={runtime?.rumble_enabled ?? false}
            disabled={!canControl || !rumbleAvailable || pendingToggle}
            onChange={(value) => void toggle(value)}
          />
          <div className="form-actions">
            <div className="page-header-action">
              <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
                {saving ? (
                  "Saving…"
                ) : (
                  <>
                    <Save size={15} />
                    Save changes
                  </>
                )}
              </Button>
              <Button
                variant="quiet"
                onClick={() => void test()}
                disabled={!canControl || !rumbleAvailable || testing}
              >
                {testing ? (
                  "Testing…"
                ) : (
                  <>
                    <TimerReset size={15} />
                    Test for 350 ms
                  </>
                )}
              </Button>
            </div>
            {dirty && <span className="dirty-label">Unsaved changes</span>}
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Haptics test bench</h2>
              <p>
                One bounded run at a time. A server-side timeout and every teardown path return motors to
                zero.
              </p>
            </div>
            <TimerReset size={18} color="var(--violet)" />
          </div>
          <div className="card-grid grid-3">
            {(
              [
                ["left", "Left motor", 0, 255],
                ["right", "Right motor", 0, 255],
                ["duration_ms", "Duration (ms)", 10, 5000],
              ] as const
            ).map(([key, label, min, max]) => (
              <Field
                key={key}
                label={label}
                help={key === "duration_ms" ? "10–5000 ms." : "0–255 intensity."}
              >
                <NumberInput
                  aria-label={label}
                  value={benchDraft[key]}
                  min={min}
                  max={max}
                  step={key === "duration_ms" ? 10 : 1}
                  disabled={
                    !canControl ||
                    !rumbleAvailable ||
                    benchPending !== null ||
                    runtime?.haptics_test?.status === "running"
                  }
                  onChange={(event) =>
                    setBenchDraft((current) => ({ ...current, [key]: Number(event.target.value) }))
                  }
                />
              </Field>
            ))}
          </div>
          <div className="form-actions">
            <div className="preview-status">
              <StatusPill
                tone={runtime?.haptics_test?.status === "running" ? "warning" : "neutral"}
                label={runtime?.haptics_test?.status?.replace("_", " ") ?? "idle"}
              />
              {runtime?.haptics_test?.status === "running" && (
                <span className="muted">
                  Ends automatically at{" "}
                  {new Date(runtime.haptics_test.expires_at * 1000).toLocaleTimeString()}
                </span>
              )}
            </div>
            <div className="page-header-action">
              <Button
                variant="quiet"
                onClick={() => void cancelBench()}
                disabled={
                  !canControl ||
                  !rumbleAvailable ||
                  benchPending !== null ||
                  runtime?.haptics_test?.status !== "running"
                }
              >
                {benchPending === "cancel" ? "Cancelling…" : "Stop and neutralize"}
              </Button>
              <Button
                onClick={() => void startBench()}
                disabled={
                  !canControl ||
                  !rumbleAvailable ||
                  benchPending !== null ||
                  runtime?.haptics_test?.status === "running"
                }
              >
                {benchPending === "start" ? "Starting…" : "Run bounded test"}
              </Button>
            </div>
          </div>
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>DSP tuning</h2>
              <p>Units and limits mirror the schema exposed by `/api/v1/config`.</p>
            </div>
          </div>
          {grouped.map(({ group, fields }) => (
            <div className="form-section" key={group}>
              <h3>{group}</h3>
              <div className="card-grid grid-2">
                {fields.map((field) => (
                  <Field
                    key={field.key}
                    label={field.label}
                    help={field.help}
                    error={fieldErrors[field.key] || fieldErrors[`rumble.${field.key}`]}
                  >
                    <NumberInput
                      aria-label={field.label}
                      value={draft[field.key]}
                      min={field.min}
                      max={field.max}
                      step={field.step}
                      disabled={coreStatus !== "online" || saving}
                      onChange={(event) => change(field.key, event.target.value)}
                    />
                  </Field>
                ))}
              </div>
            </div>
          ))}
          <div className="form-actions">
            <span className="muted">Configuration is persisted by the local core.</span>
            <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
              {saving ? "Saving…" : "Apply haptics"}
            </Button>
          </div>
        </Card>
      </div>
      {error && !(error instanceof ApiError) && <p className="muted">{errorMessage(error)}</p>}
      {stale && (
        <p className="unavailable">
          Controller values shown above are stale while the WebSocket is not online.
        </p>
      )}
    </>
  );
}
