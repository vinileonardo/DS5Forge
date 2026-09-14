"""Pure touch gesture interpretation plus a small output service."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..diagnostics.logging import get_logger
from ..domain.models import ControllerInput
from .ports import MouseOutput

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MouseAction:
    kind: str
    left: bool | None = None
    down: bool | None = None
    dx: int = 0
    dy: int = 0
    amount: int = 0
    horizontal: bool = False


@dataclass(frozen=True, slots=True)
class GestureResult:
    actions: tuple[MouseAction, ...] = ()
    mic_target: str | None = None


class GestureInterpreter:
    """State machine independent of Windows SendInput."""

    POLL_HZ = 250
    TAP_MAX_MS = 220
    TAP_MAX_MOVE = 40

    def __init__(self) -> None:
        self.prev_l3 = self.prev_r3 = False
        self.prev_mic = False
        self.prev_pad_click = False
        self.reset_state()

    def reset_state(self) -> tuple[MouseAction, ...]:
        actions: list[MouseAction] = []
        if self.prev_l3:
            actions.append(MouseAction("button", left=True, down=False))
        if self.prev_r3:
            actions.append(MouseAction("button", left=False, down=False))
        if self.prev_pad_click:
            actions.append(MouseAction("button", left=True, down=False))
        self.prev_active0 = False
        self.prev_active1 = False
        self.last_x: float | None = None
        self.last_y: float | None = None
        self.touch_start_t = 0.0
        self.touch_travel = 0.0
        self.two_finger_session = False
        self.last2_y: float | None = None
        self.last2_x: float | None = None
        self.prev_l3 = self.prev_r3 = False
        self.prev_mic = False
        self.prev_pad_click = False
        self.scroll_accum_v = 0.0
        self.scroll_accum_h = 0.0
        return tuple(actions)

    def process(
        self,
        sample: ControllerInput,
        config: dict[str, Any],
        *,
        now: float | None = None,
        trackpad_enabled: bool = True,
    ) -> GestureResult:
        actions: list[MouseAction] = []
        now = time.monotonic() if now is None else now

        mic_target = None
        if sample.mic_button and not self.prev_mic:
            mic_target = "master"
        self.prev_mic = sample.mic_button

        if sample.l3 != self.prev_l3:
            actions.append(MouseAction("button", left=True, down=sample.l3))
        if sample.r3 != self.prev_r3:
            actions.append(MouseAction("button", left=False, down=sample.r3))
        self.prev_l3, self.prev_r3 = sample.l3, sample.r3

        # L3/R3 remain mouse buttons even when touchpad gestures are disabled,
        # matching the upstream behavior. Touch samples are reset so re-enable
        # cannot turn a stale contact into a click.
        if not trackpad_enabled:
            self.prev_active0 = self.prev_active1 = False
            self.last_x = self.last_y = None
            self.last2_y = self.last2_x = None
            self.two_finger_session = False
            return GestureResult(tuple(actions), mic_target=mic_target)

        t0, t1 = sample.touch0, sample.touch1
        a0, a1 = t0.active, t1.active
        if sample.touchpad_button != self.prev_pad_click:
            actions.append(MouseAction("button", left=True, down=sample.touchpad_button))
        self.prev_pad_click = sample.touchpad_button

        if a0 and a1:
            self.two_finger_session = True
            cy = (t0.y + t1.y) / 2.0
            cx = (t0.x + t1.x) / 2.0
            if self.last2_y is not None and self.last2_x is not None:
                self.scroll_accum_v += (self.last2_y - cy) * float(config["scroll_speed"])
                self.scroll_accum_h += (cx - self.last2_x) * float(config["scroll_speed"])
                while abs(self.scroll_accum_v) >= 40:
                    step = 40 if self.scroll_accum_v > 0 else -40
                    actions.append(MouseAction("wheel", amount=step))
                    self.scroll_accum_v -= step
                while abs(self.scroll_accum_h) >= 40:
                    step = 40 if self.scroll_accum_h > 0 else -40
                    actions.append(MouseAction("wheel", amount=step, horizontal=True))
                    self.scroll_accum_h -= step
            self.last2_y, self.last2_x = cy, cx
            self.last_x = self.last_y = None
        else:
            self.last2_y = self.last2_x = None

        if a0 and not a1:
            if not self.prev_active0 or self.last_x is None or self.last_y is None:
                self.touch_start_t = now
                self.touch_travel = 0.0
            else:
                dx = t0.x - self.last_x
                dy = t0.y - self.last_y
                self.touch_travel += abs(dx) + abs(dy)
                speed = (dx * dx + dy * dy) ** 0.5
                accel = 1.0 + min(speed * float(config["acceleration"]), float(config.get("accel_cap", 1.2)))
                actions.append(
                    MouseAction(
                        "move",
                        dx=int(round(dx * float(config["pointer_speed"]) * accel)),
                        dy=int(round(dy * float(config["pointer_speed"]) * accel)),
                    )
                )
            self.last_x, self.last_y = t0.x, t0.y
        else:
            self.last_x = self.last_y = None

        if self.prev_active0 and not a0 and not a1:
            duration_ms = (now - self.touch_start_t) * 1000
            if (
                duration_ms < self.TAP_MAX_MS
                and self.touch_travel < self.TAP_MAX_MOVE
                and config.get("tap_to_click", True)
            ):
                left = not self.two_finger_session
                actions.extend(
                    (
                        MouseAction("button", left=left, down=True),
                        MouseAction("button", left=left, down=False),
                    )
                )
            self.two_finger_session = False

        self.prev_active0, self.prev_active1 = a0, a1
        return GestureResult(tuple(actions), mic_target=mic_target)


class TouchpadService:
    def __init__(
        self,
        output: MouseOutput,
        config_provider: Callable[[], dict[str, Any]],
        *,
        toggle_callback: Callable[[str], None] | None = None,
        error_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        self.output = output
        self.config_provider = config_provider
        self.toggle_callback = toggle_callback
        self.error_callback = error_callback
        self.interpreter = GestureInterpreter()
        self.enabled = True
        self._lock = threading.RLock()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            enabled = bool(enabled)
            mic_was_down = self.interpreter.prev_mic
            if self.enabled and not enabled:
                try:
                    self._execute(self.interpreter.reset_state())
                except Exception as exc:
                    self._report_error(exc)
                    self._release_all_after_failure()
            self.enabled = enabled
            if not enabled:
                self.interpreter.reset_state()
                # Disabling gestures must not turn a held microphone button
                # into a second toggle on the next controller poll.
                self.interpreter.prev_mic = mic_was_down

    def handle(self, sample: ControllerInput) -> None:
        with self._lock:
            try:
                config = self.config_provider()
                trackpad_config = config.get("trackpad", config)
                result = self.interpreter.process(sample, trackpad_config, trackpad_enabled=self.enabled)
                if result.mic_target and self.toggle_callback:
                    self.toggle_callback(config.get("mic_button", result.mic_target))
                self._execute(result.actions)
            except Exception as exc:  # platform output is an operational boundary
                LOGGER.exception("touchpad processing failed")
                # A partial synthetic sequence (for example DOWN succeeded and
                # UP failed) must never leave Windows with a logically held
                # mouse button. Reset semantic state and retry tracked releases.
                self.interpreter.reset_state()
                self._release_all_after_failure()
                if self.error_callback:
                    self.error_callback(exc)

    def reset(self) -> None:
        with self._lock:
            try:
                self._execute(self.interpreter.reset_state())
            except Exception as exc:
                self._report_error(exc)
            self.interpreter.reset_state()
            try:
                self.output.release_all()
            except Exception as exc:
                LOGGER.exception("failed to release synthesized mouse buttons")
                if self.error_callback:
                    self.error_callback(exc)

    def _release_all_after_failure(self) -> None:
        try:
            self.output.release_all()
        except Exception as cleanup_exc:
            LOGGER.exception("touchpad failure cleanup failed")
            if self.error_callback:
                self.error_callback(cleanup_exc)

    def _report_error(self, error: Exception) -> None:
        LOGGER.error(
            "touchpad output failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        if self.error_callback:
            self.error_callback(error)

    def _execute(self, actions: tuple[MouseAction, ...]) -> None:
        for action in actions:
            if action.kind == "move":
                self.output.move(action.dx, action.dy)
            elif action.kind == "button":
                self.output.button(bool(action.left), bool(action.down))
            elif action.kind == "wheel":
                self.output.wheel(action.amount, horizontal=action.horizontal)
