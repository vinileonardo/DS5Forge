import type {
  ControllerInput,
  RuntimeState,
  StickCalibration,
  StickTelemetry,
  TouchPoint,
} from "../../lib/api/contracts";

const BUTTONS: ReadonlyArray<{ key: keyof ControllerInput; label: string }> = [
  { key: "cross", label: "Cross" },
  { key: "circle", label: "Circle" },
  { key: "square", label: "Square" },
  { key: "triangle", label: "Triangle" },
  { key: "l1", label: "L1" },
  { key: "r1", label: "R1" },
  { key: "l2_button", label: "L2" },
  { key: "r2_button", label: "R2" },
  { key: "l3", label: "L3" },
  { key: "r3", label: "R3" },
  { key: "options", label: "Options" },
  { key: "share", label: "Share" },
  { key: "ps", label: "PS" },
  { key: "mic_button", label: "Mic" },
  { key: "touchpad_button", label: "Touchpad" },
];

export function DigitalInputVisualizer({ input }: { input: ControllerInput }) {
  return (
    <div className="input-visualizer" aria-label="Digital controller input state">
      <div className="dpad-visualizer" aria-label="D-pad state">
        <span className={input.dpad_up ? "pressed" : ""}>▲</span>
        <span className={input.dpad_left ? "pressed" : ""}>◀</span>
        <span className="dpad-center">＋</span>
        <span className={input.dpad_right ? "pressed" : ""}>▶</span>
        <span className={input.dpad_down ? "pressed" : ""}>▼</span>
      </div>
      <div className="button-state-grid">
        {BUTTONS.map(({ key, label }) => {
          const pressed = typeof input[key] === "boolean" && input[key];
          return (
            <span className={`button-state${pressed ? " pressed" : ""}`} key={key}>
              <span className="button-state-dot" aria-hidden="true" />
              {label}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function StickPlane({
  label,
  x,
  y,
  deadzone = 0,
}: {
  label: string;
  x: number;
  y: number;
  deadzone?: number;
}) {
  const left = `${50 + Math.max(-1, Math.min(1, x)) * 50}%`;
  const top = `${50 + Math.max(-1, Math.min(1, y)) * 50}%`;
  return (
    <div className="stick-visualizer">
      <div className="stick-plane" aria-label={`${label} XY position`}>
        <span className="stick-axis stick-axis-x" aria-hidden="true" />
        <span className="stick-axis stick-axis-y" aria-hidden="true" />
        <span
          className="stick-deadzone"
          aria-hidden="true"
          style={{ width: `${deadzone * 100}%`, height: `${deadzone * 100}%` }}
        />
        <span className="stick-dot" style={{ left, top }} aria-hidden="true" />
      </div>
      <div className="stick-caption">
        <strong>{label}</strong>
        <span>
          X {x.toFixed(2)} · Y {y.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

export function StickPairVisualizer({
  sticks,
  calibration,
}: {
  sticks: StickTelemetry;
  calibration: StickCalibration;
}) {
  return (
    <div className="stick-grid">
      <StickPlane
        label="Left stick"
        x={sticks.left_x}
        y={sticks.left_y}
        deadzone={calibration.left_deadzone}
      />
      <StickPlane
        label="Right stick"
        x={sticks.right_x}
        y={sticks.right_y}
        deadzone={calibration.right_deadzone}
      />
    </div>
  );
}

export function TriggerMeter({ label, value, digital }: { label: string; value: number; digital: boolean }) {
  return (
    <div className="trigger-meter">
      <div className="trigger-meter-heading">
        <strong>{label}</strong>
        <span>{Math.round(value * 100)}%</span>
      </div>
      <div
        className="trigger-track"
        role="meter"
        aria-label={`${label} analog value`}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value}
      >
        <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
      <span className="muted">Digital: {digital ? "pressed" : "released"}</span>
    </div>
  );
}

export function TouchPointVisualizer({ point, index }: { point: TouchPoint; index: number }) {
  const x = Math.max(0, Math.min(1, point.x / 1920));
  const y = Math.max(0, Math.min(1, point.y / 1080));
  return (
    <span
      className={`touch-point${point.active ? " active" : ""}`}
      style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
      aria-label={`Touch ${index + 1} ${point.active ? "active" : "inactive"}`}
    >
      {point.active ? index + 1 : ""}
    </span>
  );
}

export function TouchSurfaceVisualizer({ points }: { points: readonly [TouchPoint, TouchPoint] }) {
  const activeCount = points.filter((point) => point.active).length;
  return (
    <div className="touch-surface" aria-label={`Touchpad visualization, ${activeCount} active points`}>
      <span className="touch-surface-label">DualSense touchpad</span>
      {points.map((point, index) => (
        <TouchPointVisualizer key={index} point={point} index={index} />
      ))}
      <span className="touch-surface-status">{activeCount} / 2 points active</span>
    </div>
  );
}

export function availableCapabilityCount(runtime: RuntimeState | null): number {
  if (!runtime) return 0;
  return Object.entries(runtime.capabilities).filter(
    ([name, value]) => name !== "availability" && value === true,
  ).length;
}

export function capabilityEnabled(
  runtime: {
    capabilities: {
      usb: boolean;
      rumble: boolean;
      touchpad: boolean;
      microphone_button: boolean;
      lightbar: boolean;
      adaptive_triggers: boolean;
      availability?: Record<string, { supported: boolean; available: boolean; reason: string | null }>;
    };
  } | null,
  name: "rumble" | "touchpad" | "lightbar" | "adaptive_triggers",
): boolean {
  if (!runtime) return false;
  const entry = runtime.capabilities.availability?.[name];
  if (entry) return entry.supported && entry.available;
  return runtime.capabilities[name];
}

export function capabilityReason(
  runtime: {
    capabilities: {
      availability?: Record<string, { supported: boolean; available: boolean; reason: string | null }>;
    };
  } | null,
  name: string,
): string {
  return (
    runtime?.capabilities.availability?.[name]?.reason ??
    "The connected adapter does not expose this capability."
  );
}
