import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ControllerInput, RuntimeState, StickCalibration } from "../../lib/api/contracts";
import {
  DigitalInputVisualizer,
  StickPairVisualizer,
  TouchSurfaceVisualizer,
  TriggerMeter,
  availableCapabilityCount,
  capabilityEnabled,
  capabilityReason,
} from "./visualizers";

const input: ControllerInput = {
  square: false,
  triangle: false,
  circle: false,
  cross: true,
  dpad_up: true,
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
  l2: 0.75,
  r2: 0,
  sticks: { left_x: 0.5, left_y: -0.5, right_x: 0, right_y: 0 },
  touch0: { active: true, x: 960, y: 540 },
  touch1: { active: false, x: 0, y: 0 },
  buttons: { cross: true },
};

const calibration: StickCalibration = {
  left_deadzone: 0.1,
  right_deadzone: 0.08,
  left_center_x: 0,
  left_center_y: 0,
  right_center_x: 0,
  right_center_y: 0,
};

describe("Controller Lab visualizers", () => {
  it("renders button, stick, trigger and touch state", () => {
    render(
      <>
        <DigitalInputVisualizer input={input} />
        <TriggerMeter label="L2" value={input.l2} digital={input.l2_button} />
        <StickPairVisualizer sticks={input.sticks} calibration={calibration} />
        <TouchSurfaceVisualizer points={[input.touch0, input.touch1]} />
      </>,
    );

    expect(screen.getByText("Cross").className).toContain("pressed");
    expect(screen.getByLabelText("Left stick XY position")).toBeVisible();
    expect(screen.getByLabelText("Touchpad visualization, 1 active points")).toBeVisible();
    expect(screen.getByLabelText("Touch 1 active")).toBeVisible();
  });

  it("gates unsupported capabilities and provides a reason", () => {
    const runtime = {
      capabilities: {
        usb: true,
        rumble: true,
        touchpad: true,
        microphone_button: true,
        lightbar: true,
        adaptive_triggers: false,
        availability: {
          adaptive_triggers: { supported: false, available: false, reason: "Library surface unavailable" },
        },
      },
    };
    expect(capabilityEnabled(runtime, "adaptive_triggers")).toBe(false);
    expect(capabilityReason(runtime, "adaptive_triggers")).toBe("Library surface unavailable");
  });

  it("counts only boolean capability flags and ignores the availability map", () => {
    const runtime = {
      capabilities: {
        usb: true,
        rumble: true,
        touchpad: false,
        microphone_button: true,
        lightbar: true,
        adaptive_triggers: false,
        availability: {
          usb: { supported: true, available: true, reason: null },
          rumble: { supported: true, available: true, reason: null },
        },
      },
    } as unknown as RuntimeState;
    expect(availableCapabilityCount(runtime)).toBe(4);
    expect(availableCapabilityCount(null)).toBe(0);
  });
});
