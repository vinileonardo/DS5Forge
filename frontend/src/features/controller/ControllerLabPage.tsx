import { Gamepad2, Lightbulb, RotateCcw, Save, TimerReset, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Button,
  Card,
  ErrorText,
  Field,
  Notice,
  NumberInput,
  PageHeader,
  Select,
  StatusPill,
  Toggle,
} from "../../components/ui";
import type {
  ControllerInput,
  LightbarState,
  PlayerLedState,
  StickCalibration,
  TriggerEffect,
  TriggerPreview,
} from "../../lib/api/contracts";
import { useI18n } from "../../lib/i18n";
import { useRuntime } from "../../lib/runtime/RuntimeProvider";
import {
  DigitalInputVisualizer,
  StickPairVisualizer,
  TouchSurfaceVisualizer,
  TriggerMeter,
  capabilityEnabled,
  capabilityReason,
} from "./visualizers";

type LabTab = "input" | "triggers" | "lighting" | "sticks";

const tabs: ReadonlyArray<{ id: LabTab; label: string }> = [
  { id: "input", label: "Input" },
  { id: "triggers", label: "Triggers" },
  { id: "lighting", label: "Lighting" },
  { id: "sticks", label: "Sticks" },
];

const EMPTY_INPUT: ControllerInput = {
  square: false,
  triangle: false,
  circle: false,
  cross: false,
  dpad_up: false,
  dpad_down: false,
  dpad_left: false,
  dpad_right: false,
  l1: false,
  r1: false,
  l2_button: false,
  r2_button: false,
  l3: false,
  r3: false,
  options: false,
  share: false,
  ps: false,
  mic_button: false,
  touchpad_button: false,
  l2: 0,
  r2: 0,
  sticks: { left_x: 0, left_y: 0, right_x: 0, right_y: 0 },
  touch0: { active: false, x: 0, y: 0 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: {},
};

const EMPTY_EFFECT: TriggerEffect = {
  mode: "off",
  start_position: 0,
  end_position: 255,
  force: 0,
  frequency: 0,
  amplitude: 0,
};

const EMPTY_LIGHTBAR: LightbarState = {
  r: 0,
  g: 0,
  b: 0,
  enabled: true,
  brightness: 2,
  pulse: "off",
};

const EMPTY_CALIBRATION: StickCalibration = {
  left_deadzone: 0.08,
  right_deadzone: 0.08,
  left_center_x: 0,
  left_center_y: 0,
  right_center_x: 0,
  right_center_y: 0,
};

const TRIGGER_PRESETS: ReadonlyArray<{
  label: string;
  description: string;
  effect: TriggerEffect;
}> = [
  { label: "Off", description: "Neutral trigger output", effect: EMPTY_EFFECT },
  {
    label: "Resistance",
    description: "Moderate continuous resistance",
    effect: {
      mode: "resistance",
      start_position: 0,
      end_position: 255,
      force: 100,
      frequency: 0,
      amplitude: 0,
    },
  },
  {
    label: "Pulse",
    description: "Bounded pulsing resistance",
    effect: {
      mode: "pulse",
      start_position: 40,
      end_position: 200,
      force: 80,
      frequency: 8,
      amplitude: 120,
    },
  },
];

function localCapability(
  runtime: ReturnType<typeof useRuntime>["runtime"],
  name: "lightbar" | "adaptive_triggers",
) {
  return capabilityEnabled(runtime, name);
}

export function ControllerLabPage() {
  const { runtime, coreStatus, stale, canControl } = useRuntime();
  const [tab, setTab] = useState<LabTab>("input");
  const input = runtime?.input ?? EMPTY_INPUT;
  const telemetry = runtime?.telemetry;

  return (
    <>
      <PageHeader
        eyebrow="Controller Lab"
        title="Controller Lab"
        description="Inspect the live wired DualSense signal and safely preview supported output features. The Python core remains the hardware authority."
        action={
          <StatusPill
            tone={stale || coreStatus !== "online" ? "warning" : "success"}
            label={stale ? "Stale" : coreStatus === "online" ? "Live" : "Offline"}
            detail={telemetry ? `${telemetry.sample_rate_hz.toFixed(0)} Hz` : "USB"}
          />
        }
      />
      {(coreStatus !== "online" || stale || !runtime) && (
        <Notice tone="warning" title={runtime ? "Controller state is stale" : "Controller unavailable"}>
          Live controls stay disabled until a validated WebSocket snapshot reports an online connected USB
          controller. Previously received values are shown as stale telemetry.
        </Notice>
      )}
      <div className="lab-tabs" role="tablist" aria-label="Controller Lab sections">
        {tabs.map(({ id, label }) => (
          <button
            className={`lab-tab${tab === id ? " active" : ""}`}
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            aria-controls={`controller-lab-${id}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "input" && <InputTab input={input} runtime={runtime} stale={stale} />}
      {tab === "triggers" && <TriggersTab runtime={runtime} canControl={canControl && !stale} />}
      {tab === "lighting" && <LightingTab runtime={runtime} canControl={canControl && !stale} />}
      {tab === "sticks" && (
        <SticksTab runtime={runtime} input={input} canControl={coreStatus === "online" && !stale} />
      )}
    </>
  );
}

function InputTab({
  input,
  runtime,
  stale,
}: {
  input: ControllerInput;
  runtime: ReturnType<typeof useRuntime>["runtime"];
  stale: boolean;
}) {
  return (
    <div className="stack" id="controller-lab-input" role="tabpanel">
      <Card>
        <div className="card-header">
          <div>
            <h2>Digital input</h2>
            <p>Button and D-pad state is sampled internally at the USB read cadence.</p>
          </div>
          <Gamepad2 size={18} color="var(--accent)" />
        </div>
        <DigitalInputVisualizer input={input} />
      </Card>
      <div className="card-grid grid-2">
        <Card>
          <div className="card-header">
            <div>
              <h2>Analog controls</h2>
              <p>Values are normalized by the core before they cross the API boundary.</p>
            </div>
          </div>
          <div className="trigger-stack">
            <TriggerMeter label="L2" value={input.l2} digital={input.l2_button} />
            <TriggerMeter label="R2" value={input.r2} digital={input.r2_button} />
          </div>
          <StickPairVisualizer
            sticks={input.sticks}
            calibration={runtime?.stick_calibration ?? EMPTY_CALIBRATION}
          />
        </Card>
        <Card>
          <div className="card-header">
            <div>
              <h2>Touch surface</h2>
              <p>Raw points are informational; touch gestures remain owned by the core.</p>
            </div>
          </div>
          <TouchSurfaceVisualizer points={[input.touch0, input.touch1]} />
          <dl className="data-list lab-data-list">
            <div className="data-item">
              <dt>Touchpad button</dt>
              <dd className={input.touchpad_button ? "good" : ""}>
                {input.touchpad_button ? "Pressed" : "Released"}
              </dd>
            </div>
            <div className="data-item">
              <dt>Telemetry</dt>
              <dd>{stale ? "Stale" : (runtime?.telemetry?.sequence ?? "—")}</dd>
            </div>
          </dl>
        </Card>
      </div>
    </div>
  );
}

function TriggersTab({
  runtime,
  canControl,
}: {
  runtime: ReturnType<typeof useRuntime>["runtime"];
  canControl: boolean;
}) {
  const { applyTriggers, previewTriggers, cancelTriggerPreview, resetTriggers } = useRuntime();
  const supported = localCapability(runtime, "adaptive_triggers");
  const current = runtime?.triggers;
  const [draft, setDraft] = useState({
    left: current?.left ?? EMPTY_EFFECT,
    right: current?.right ?? EMPTY_EFFECT,
  });
  const [duration, setDuration] = useState(1000);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<"apply" | "preview" | "reset" | "cancel" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!dirty && current) setDraft({ left: current.left, right: current.right });
  }, [current, dirty]);

  function change(side: "left" | "right", key: keyof TriggerEffect, rawValue: string) {
    setDirty(true);
    setMessage(null);
    setDraft((state) => ({
      ...state,
      [side]: { ...state[side], [key]: key === "mode" ? rawValue : Number(rawValue) },
    }));
  }

  function choosePreset(effect: TriggerEffect) {
    setDirty(true);
    setMessage(null);
    setDraft({ left: { ...effect }, right: { ...effect } });
  }

  async function apply() {
    setPending("apply");
    setError(null);
    try {
      const result = await applyTriggers(draft);
      setDraft({ left: result.left, right: result.right });
      setDirty(false);
      setMessage("Adaptive-trigger settings applied.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function preview() {
    setPending("preview");
    setError(null);
    try {
      await previewTriggers(draft, duration);
      setMessage("Preview active; both triggers will reset automatically.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function cancel() {
    setPending("cancel");
    setError(null);
    try {
      await cancelTriggerPreview();
      setMessage("Trigger preview cancelled and outputs reset.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function reset() {
    setPending("reset");
    setError(null);
    try {
      const result = await resetTriggers();
      setDraft({ left: result.left, right: result.right });
      setDirty(false);
      setMessage("Both adaptive triggers reset to Off.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="stack" id="controller-lab-triggers" role="tabpanel">
      {!supported && runtime && (
        <Notice tone="warning" title="Adaptive triggers unavailable">
          {capabilityReason(runtime, "adaptive_triggers")} No trigger command is sent to the adapter.
        </Notice>
      )}
      <ErrorText error={error} />
      {message && (
        <Notice tone="success" title="Controller Lab">
          {message}
        </Notice>
      )}
      <Card>
        <div className="card-header">
          <div>
            <h2>Trigger effects</h2>
            <p>Configure left and right effects, then apply or preview them for a bounded interval.</p>
          </div>
          <Zap size={18} color="var(--violet)" />
        </div>
        <div className="preset-strip" aria-label="Trigger presets">
          <span className="muted">Presets only change the draft:</span>
          {TRIGGER_PRESETS.map((preset) => (
            <Button
              key={preset.label}
              variant="quiet"
              title={preset.description}
              disabled={!canControl || !supported || pending !== null}
              onClick={() => choosePreset(preset.effect)}
            >
              {preset.label}
            </Button>
          ))}
        </div>
        <div className="card-grid grid-2">
          {(["left", "right"] as const).map((side) => (
            <TriggerEditor
              key={side}
              side={side}
              effect={draft[side]}
              disabled={!canControl || !supported || pending !== null}
              onChange={change}
            />
          ))}
        </div>
        <div className="form-actions">
          <span className="muted">{dirty ? "Unsaved trigger draft" : "Trigger draft matches the core."}</span>
          <div className="page-header-action">
            <Button
              variant="quiet"
              onClick={() => void reset()}
              disabled={!canControl || !supported || pending !== null}
            >
              <RotateCcw size={15} /> Reset
            </Button>
            <Button
              onClick={() => void apply()}
              disabled={!canControl || !supported || !dirty || pending !== null}
            >
              <Save size={15} /> {pending === "apply" ? "Applying…" : "Apply"}
            </Button>
          </div>
        </div>
      </Card>
      <Card>
        <div className="card-header">
          <div>
            <h2>Bounded preview</h2>
            <p>
              The server owns the timeout and resets both trigger outputs on timeout, cancel, reconnect or
              shutdown.
            </p>
          </div>
          <TimerReset size={18} color="var(--accent)" />
        </div>
        <div className="card-grid grid-2">
          <Field label="Duration" help="10–5000 ms; the server rejects values outside this range.">
            <NumberInput
              value={duration}
              min={10}
              max={5000}
              step={10}
              disabled={!canControl || !supported || pending !== null}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </Field>
          <div className="preview-state-box">
            <PreviewStatus preview={current?.preview ?? null} />
          </div>
        </div>
        <div className="form-actions">
          <span className="muted">Preview is intentionally single-flight.</span>
          <div className="page-header-action">
            <Button
              variant="quiet"
              onClick={() => void cancel()}
              disabled={
                !canControl || !supported || current?.preview?.status !== "running" || pending !== null
              }
            >
              {pending === "cancel" ? "Cancelling…" : "Cancel preview"}
            </Button>
            <Button
              onClick={() => void preview()}
              disabled={
                !canControl || !supported || pending !== null || current?.preview?.status === "running"
              }
            >
              {pending === "preview" ? "Starting…" : "Preview"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function TriggerEditor({
  side,
  effect,
  disabled,
  onChange,
}: {
  side: "left" | "right";
  effect: TriggerEffect;
  disabled: boolean;
  onChange: (side: "left" | "right", key: keyof TriggerEffect, value: string) => void;
}) {
  return (
    <div className="lab-editor">
      <h3>{side === "left" ? "L2 / left" : "R2 / right"}</h3>
      <Field label="Mode" help="Off is the neutral hardware state.">
        <Select
          value={effect.mode}
          disabled={disabled}
          onChange={(event) => onChange(side, "mode", event.target.value)}
        >
          <option value="off">Off</option>
          <option value="resistance">Resistance</option>
          <option value="pulse">Pulse</option>
          <option value="rigid">Rigid</option>
        </Select>
      </Field>
      <div className="card-grid grid-2">
        {(
          [
            ["start_position", "Start position"],
            ["end_position", "End position"],
            ["force", "Force"],
            ["frequency", "Frequency"],
            ["amplitude", "Amplitude"],
          ] as const
        ).map(([key, label]) => (
          <Field key={key} label={label}>
            <NumberInput
              value={effect[key]}
              min={0}
              max={255}
              step={1}
              disabled={disabled}
              onChange={(event) => onChange(side, key, event.target.value)}
            />
          </Field>
        ))}
      </div>
    </div>
  );
}

function PreviewStatus({ preview }: { preview: TriggerPreview | null }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!preview || preview.status !== "running") return undefined;
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 100);
    return () => window.clearInterval(timer);
  }, [preview]);
  if (!preview) return <span className="muted">No preview running.</span>;
  const remaining = Math.max(0, preview.expires_at - now);
  return (
    <div className="preview-status">
      <StatusPill
        tone={
          preview.status === "running" ? "warning" : preview.status === "timed_out" ? "neutral" : "success"
        }
        label={preview.status.replace("_", " ")}
      />
      {preview.status === "running" && <strong>{remaining.toFixed(1)} s remaining</strong>}
      {preview.error && <span className="inline-error">{preview.error.message}</span>}
    </div>
  );
}

function LightingTab({
  runtime,
  canControl,
}: {
  runtime: ReturnType<typeof useRuntime>["runtime"];
  canControl: boolean;
}) {
  const { applyLightbar, resetLightbar, applyPlayerLeds, resetPlayerLeds } = useRuntime();
  const { t } = useI18n();
  const supported = localCapability(runtime, "lightbar");
  const current = runtime?.lightbar ?? EMPTY_LIGHTBAR;
  const currentPlayerLeds: PlayerLedState = useMemo(
    () => runtime?.player_leds ?? { enabled: true, intensity: 1 },
    [runtime?.player_leds],
  );
  const [draft, setDraft] = useState(current);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<"apply" | "reset" | "player-leds" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [playerLeds, setPlayerLeds] = useState<PlayerLedState>(currentPlayerLeds);
  const [playerLedsDirty, setPlayerLedsDirty] = useState(false);

  useEffect(() => {
    if (!dirty) setDraft(current);
  }, [current, dirty]);

  useEffect(() => {
    if (!playerLedsDirty) setPlayerLeds(currentPlayerLeds);
  }, [currentPlayerLeds, playerLedsDirty]);

  async function savePlayerLeds() {
    setPending("player-leds");
    setError(null);
    try {
      const result = await applyPlayerLeds(playerLeds);
      setPlayerLeds(result);
      setPlayerLedsDirty(false);
      setMessage("Player LED state applied.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function clearPlayerLeds() {
    setPending("player-leds");
    setError(null);
    try {
      const result = await resetPlayerLeds();
      setPlayerLeds(result);
      setPlayerLedsDirty(false);
      setMessage("Player LED state reset.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  function update(patch: Partial<LightbarState>) {
    setDirty(true);
    setMessage(null);
    setDraft((value) => ({ ...value, ...patch }));
  }

  async function apply() {
    setPending("apply");
    setError(null);
    try {
      const result = await applyLightbar(draft);
      setDraft(result);
      setDirty(false);
      setMessage("Lightbar settings applied.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function reset() {
    setPending("reset");
    setError(null);
    try {
      const result = await resetLightbar();
      setDraft(result);
      setDirty(false);
      setMessage("Lightbar reset.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  const hex = `#${[draft.r, draft.g, draft.b].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
  return (
    <div className="stack" id="controller-lab-lighting" role="tabpanel">
      {!supported && runtime && (
        <Notice tone="warning" title="Lightbar unavailable">
          {capabilityReason(runtime, "lightbar")} No lightbar command is sent to the adapter.
        </Notice>
      )}
      <ErrorText error={error} />
      {message && (
        <Notice tone="success" title="Controller Lab">
          {message}
        </Notice>
      )}
      <Card>
        <div className="card-header">
          <div>
            <h2>Lightbar</h2>
            <p>Color and presentation settings are applied only after server validation.</p>
          </div>
          <Lightbulb size={18} color="var(--accent)" />
        </div>
        <div
          className="lightbar-preview"
          style={{
            backgroundColor: draft.enabled ? hex : "transparent",
            boxShadow: draft.enabled ? `0 0 40px ${hex}` : "none",
          }}
        >
          <span>{draft.enabled ? hex.toUpperCase() : "Disabled"}</span>
        </div>
        <div className="card-grid grid-2">
          <Field label="Color" help="RGB values are sent through the typed local API.">
            <div className="color-input-row">
              <input
                className="color-input"
                type="color"
                value={hex}
                disabled={!canControl || !supported || pending !== null}
                aria-label="Lightbar color"
                onChange={(event) => {
                  const value = event.target.value.slice(1);
                  update({
                    r: parseInt(value.slice(0, 2), 16),
                    g: parseInt(value.slice(2, 4), 16),
                    b: parseInt(value.slice(4, 6), 16),
                  });
                }}
              />
              <span className="muted">{hex.toUpperCase()}</span>
            </div>
          </Field>
          <Field label={t("controller.lightbarIntensity")} help={t("controller.lightbarIntensityHelp")}>
            <input
              className="input"
              type="range"
              min={0}
              max={100}
              step={1}
              aria-label={t("controller.lightbarIntensity")}
              value={Math.round((draft.intensity ?? 1) * 100)}
              disabled={!canControl || !supported || pending !== null}
              onChange={(event) => update({ intensity: Number(event.target.value) / 100 })}
            />
            <span className="muted">{Math.round((draft.intensity ?? 1) * 100)}%</span>
          </Field>
          <Field
            label="Pulse"
            help="Presentation hint retained in the profile; physical support is verified on Windows USB hardware."
          >
            <Select
              value={draft.pulse}
              disabled={!canControl || !supported || pending !== null}
              onChange={(event) => update({ pulse: event.target.value as LightbarState["pulse"] })}
            >
              <option value="off">Off</option>
              <option value="slow">Slow</option>
              <option value="fast">Fast</option>
            </Select>
          </Field>
          <Toggle
            label="Lightbar enabled"
            description="Disable output without changing the saved RGB values."
            checked={draft.enabled}
            disabled={!canControl || !supported || pending !== null}
            onChange={(enabled) => update({ enabled })}
          />
        </div>
        <div className="form-actions">
          <span className="muted">{dirty ? "Unsaved lighting draft" : "Lighting matches the core."}</span>
          <div className="page-header-action">
            <Button
              variant="quiet"
              onClick={() => void reset()}
              disabled={!canControl || !supported || pending !== null}
            >
              {pending === "reset" ? "Resetting…" : "Reset"}
            </Button>
            <Button
              onClick={() => void apply()}
              disabled={!canControl || !supported || !dirty || pending !== null}
            >
              <Save size={15} /> {pending === "apply" ? "Applying…" : "Apply"}
            </Button>
          </div>
        </div>
      </Card>
      <Card>
        <div className="card-header">
          <div>
            <h2>{t("controller.playerLeds")}</h2>
            <p>{t("controller.playerLedsHelp")}</p>
          </div>
          <Lightbulb size={18} color="var(--violet)" />
        </div>
        <div className="card-grid grid-2">
          <Field label={t("controller.playerLedsIntensity")}>
            <input
              className="input"
              type="range"
              min={0}
              max={100}
              step={1}
              aria-label={t("controller.playerLedsIntensity")}
              value={Math.round(playerLeds.intensity * 100)}
              disabled={!canControl || !supported || pending !== null}
              onChange={(event) => {
                setPlayerLedsDirty(true);
                setMessage(null);
                setPlayerLeds((value) => ({ ...value, intensity: Number(event.target.value) / 100 }));
              }}
            />
            <span className="muted">{Math.round(playerLeds.intensity * 100)}%</span>
          </Field>
          <Toggle
            label={t("controller.playerLedsEnabled")}
            description={t("controller.playerLedsHelp")}
            checked={playerLeds.enabled}
            disabled={!canControl || !supported || pending !== null}
            onChange={(enabled) => {
              setPlayerLedsDirty(true);
              setMessage(null);
              setPlayerLeds((value) => ({ ...value, enabled }));
            }}
          />
        </div>
        <div className="form-actions">
          <Button
            variant="quiet"
            onClick={() => void clearPlayerLeds()}
            disabled={!canControl || !supported || pending !== null}
          >
            {pending === "player-leds" ? "Working…" : "Reset Player LEDs"}
          </Button>
          <Button
            onClick={() => void savePlayerLeds()}
            disabled={!canControl || !supported || !playerLedsDirty || pending !== null}
          >
            <Save size={15} /> {pending === "player-leds" ? "Applying…" : "Apply Player LEDs"}
          </Button>
        </div>
      </Card>
    </div>
  );
}

function SticksTab({
  runtime,
  input,
  canControl,
}: {
  runtime: ReturnType<typeof useRuntime>["runtime"];
  input: ControllerInput;
  canControl: boolean;
}) {
  const { updateStickCalibration } = useRuntime();
  const { t } = useI18n();
  const current = runtime?.stick_calibration ?? EMPTY_CALIBRATION;
  const [draft, setDraft] = useState(current);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!dirty) setDraft(current);
  }, [current, dirty]);

  function update(key: keyof StickCalibration, value: string) {
    setDirty(true);
    setMessage(null);
    setDraft((state) => ({ ...state, [key]: Number(value) }));
  }

  async function save() {
    setPending(true);
    setError(null);
    try {
      const result = await updateStickCalibration(draft);
      setDraft(result);
      setDirty(false);
      setMessage("Stick visualization metadata saved.");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack" id="controller-lab-sticks" role="tabpanel">
      <Notice tone="info" title="Calibration scope">
        {t("controller.calibrationHint")}
      </Notice>
      <ErrorText error={error} />
      {message && (
        <Notice tone="success" title="Controller Lab">
          {message}
        </Notice>
      )}
      <Card>
        <div className="card-header">
          <div>
            <h2>Live stick planes</h2>
            <p>The outlined circle shows the configured deadzone; the dot is the latest validated sample.</p>
          </div>
        </div>
        <StickPairVisualizer sticks={input.sticks} calibration={draft} />
      </Card>
      <Card>
        <div className="card-header">
          <div>
            <h2>Calibration metadata</h2>
            <p>Values are bounded and persisted atomically with full profiles.</p>
          </div>
          <Gamepad2 size={18} color="var(--violet)" />
        </div>
        <div className="card-grid grid-2">
          <Field label={`Left deadzone · ${draft.left_deadzone.toFixed(2)}`} help="0–1 normalized radius.">
            <input
              className="range-input"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={draft.left_deadzone}
              disabled={!canControl || pending}
              onChange={(event) => update("left_deadzone", event.target.value)}
            />
          </Field>
          <Field label={`Right deadzone · ${draft.right_deadzone.toFixed(2)}`} help="0–1 normalized radius.">
            <input
              className="range-input"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={draft.right_deadzone}
              disabled={!canControl || pending}
              onChange={(event) => update("right_deadzone", event.target.value)}
            />
          </Field>
          {(
            [
              ["left_center_x", "Left center X"],
              ["left_center_y", "Left center Y"],
              ["right_center_x", "Right center X"],
              ["right_center_y", "Right center Y"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <NumberInput
                value={draft[key]}
                min={-1}
                max={1}
                step={0.01}
                disabled={!canControl || pending}
                onChange={(event) => update(key, event.target.value)}
              />
            </Field>
          ))}
        </div>
        <div className="form-actions">
          <span className="muted">
            {dirty ? "Unsaved calibration metadata" : "Calibration metadata is up to date."}
          </span>
          <Button onClick={() => void save()} disabled={!canControl || !dirty || pending}>
            <Save size={15} /> {pending ? "Saving…" : "Save metadata"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
