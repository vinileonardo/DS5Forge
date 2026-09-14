import { MousePointer2, Save, Touchpad as TouchpadIcon } from "lucide-react";
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
  Toggle,
} from "../../components/ui";
import { TRACKPAD_FIELD_SPECS, type TrackpadConfig } from "../../lib/api/contracts";
import { ApiError, fieldErrorMap } from "../../lib/api/errors";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";
import { TouchSurfaceVisualizer } from "../controller/visualizers";

export function TouchpadPage() {
  const { config, runtime, coreStatus, stale, canControl, updateConfig, setTouchpad } = useRuntime();
  const [draft, setDraft] = useState<TrackpadConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingToggle, setPendingToggle] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const dirty = useMemo(
    () => Boolean(config && draft && JSON.stringify(config.trackpad) !== JSON.stringify(draft)),
    [config, draft],
  );

  useEffect(() => {
    if (config && !dirty) setDraft(config.trackpad);
  }, [config, dirty]);

  if (!config || !draft) {
    return coreStatus === "online" ? (
      <LoadingState label="Waiting for touchpad configuration from the local core…" />
    ) : (
      <>
        <PageHeader
          eyebrow="Pointer and gestures"
          title="Touchpad"
          description="Configure the current DualSense touchpad-to-Windows mouse behavior."
        />
        <EmptyState
          title="Touchpad configuration unavailable"
          description="Start the local core to load persisted touchpad values. The browser will retry without creating defaults."
        />
      </>
    );
  }
  const currentDraft = draft;

  function change(key: keyof TrackpadConfig, value: string | boolean) {
    setMessage(null);
    setFieldErrors((current) => ({ ...current, [key]: "" }));
    setDraft((current) =>
      current ? { ...current, [key]: typeof value === "boolean" ? value : Number(value) } : current,
    );
  }

  async function save() {
    setSaving(true);
    setError(null);
    setMessage(null);
    setFieldErrors({});
    try {
      const saved = await updateConfig({ trackpad: currentDraft });
      setDraft(saved.trackpad);
      setMessage("Touchpad configuration saved.");
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
      await setTouchpad(enabled);
      setMessage(enabled ? "Touchpad mouse output enabled." : "Touchpad mouse output disabled.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPendingToggle(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Pointer and gestures"
        title="Touchpad"
        description="Configure the current DualSense touchpad-to-Windows mouse behavior and the gesture settings used by the core."
      />
      {coreStatus !== "online" && (
        <Notice tone="warning" title="Core unavailable">
          Persisted touchpad values are shown only when received from the core; live actions will be disabled.
        </Notice>
      )}
      {message && (
        <Notice tone="success" title="Done">
          {message}
        </Notice>
      )}
      <ErrorText error={error} />
      <div className="stack">
        <Card>
          <div className="card-header">
            <div>
              <h2>Live touch input</h2>
              <p>
                Points and the touchpad button are read by the core and shown at the bounded telemetry rate.
              </p>
            </div>
            <TouchpadIcon size={18} color="var(--accent)" />
          </div>
          {runtime?.input ? (
            <>
              <TouchSurfaceVisualizer points={[runtime.input.touch0, runtime.input.touch1]} />
              <dl className="data-list lab-data-list">
                <div className="data-item">
                  <dt>Touchpad button</dt>
                  <dd className={runtime.input.touchpad_button ? "good" : ""}>
                    {runtime.input.touchpad_button ? "Pressed" : "Released"}
                  </dd>
                </div>
                <div className="data-item">
                  <dt>State freshness</dt>
                  <dd>{stale ? "Stale" : "Live"}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="muted">Waiting for a validated controller input snapshot.</p>
          )}
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Live behavior</h2>
              <p>These controls affect the current controller session.</p>
            </div>
            <TouchpadIcon size={18} color="var(--accent)" />
          </div>
          <Toggle
            label="Touchpad mouse output"
            description={
              canControl
                ? "One-finger pointer, tap and two-finger gestures are active."
                : "Requires an online connected controller."
            }
            checked={runtime?.touchpad_enabled ?? false}
            disabled={!canControl || pendingToggle}
            onChange={(value) => void toggle(value)}
          />
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Pointer behavior</h2>
              <p>Changes are validated and persisted by the local Python core.</p>
            </div>
            <MousePointer2 size={18} color="var(--violet)" />
          </div>
          <div className="form-section">
            <div className="card-grid grid-2">
              {TRACKPAD_FIELD_SPECS.map((field) => (
                <Field
                  key={field.key}
                  label={field.label}
                  help={field.help}
                  error={fieldErrors[field.key] || fieldErrors[`trackpad.${field.key}`]}
                >
                  <NumberInput
                    aria-label={field.label}
                    value={draft[field.key] as number}
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    disabled={coreStatus !== "online" || saving}
                    onChange={(event) => change(field.key, event.target.value)}
                  />
                </Field>
              ))}
            </div>
            <Field
              label="Enabled on start"
              help="Whether touchpad mouse output starts enabled when the core connects."
            >
              <Toggle
                label="Start enabled"
                description="Apply on the next controller session."
                checked={draft.trackpad_enabled_on_start}
                disabled={coreStatus !== "online" || saving}
                onChange={(value) => change("trackpad_enabled_on_start", value)}
              />
            </Field>
            <Field
              label="Tap to click"
              help="A single-finger tap produces a left click; two-finger tap follows the existing core behavior."
            >
              <Toggle
                label="Tap gestures"
                description="Keep the current upstream tap behavior."
                checked={draft.tap_to_click}
                disabled={coreStatus !== "online" || saving}
                onChange={(value) => change("tap_to_click", value)}
              />
            </Field>
            <Field
              label="Gestures"
              help="Gesture interpretation is performed by the Python core; this only changes its validated configuration."
            >
              <Toggle
                label="Enable gestures"
                description="Allow gesture actions in the current touchpad session."
                checked={draft.gestures_enabled}
                disabled={coreStatus !== "online" || saving}
                onChange={(value) => change("gestures_enabled", value)}
              />
              <Toggle
                label="Two-finger scroll"
                description="Keep semantic vertical and horizontal scroll output."
                checked={draft.two_finger_scroll}
                disabled={coreStatus !== "online" || saving}
                onChange={(value) => change("two_finger_scroll", value)}
              />
              <Toggle
                label="Swipe gestures"
                description="Enable configured swipe interpretation when supported by the core."
                checked={draft.swipe_enabled}
                disabled={coreStatus !== "online" || saving}
                onChange={(value) => change("swipe_enabled", value)}
              />
            </Field>
            <Field
              label="Swipe threshold"
              help="Minimum movement in touchpad coordinates before a swipe is recognized (1–500)."
              error={fieldErrors.swipe_threshold || fieldErrors["trackpad.swipe_threshold"]}
            >
              <NumberInput
                aria-label="Swipe threshold"
                value={draft.swipe_threshold}
                min={1}
                max={500}
                step={1}
                disabled={coreStatus !== "online" || saving}
                onChange={(event) => change("swipe_threshold", event.target.value)}
              />
            </Field>
          </div>
          <div className="form-actions">
            <span className="muted">{dirty ? "Unsaved changes" : "Configuration is up to date."}</span>
            <Button onClick={() => void save()} disabled={!dirty || saving || coreStatus !== "online"}>
              <Save size={15} />
              {saving ? "Saving…" : "Save touchpad"}
            </Button>
          </div>
        </Card>
      </div>
      {stale && <p className="unavailable">Live controller state is stale until the WebSocket reconnects.</p>}
    </>
  );
}
