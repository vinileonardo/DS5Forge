"""Lazy `pydualsense` USB adapter."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from types import MethodType
from typing import Any

from ...diagnostics.logging import get_logger
from ...domain.errors import (
    CapabilityUnavailableError,
    ControllerUnavailableError,
    DS5ForgeError,
    ErrorCode,
    PlatformUnavailableError,
)
from ...domain.models import (
    AdaptiveTriggerEffect,
    BatterySnapshot,
    CapabilityAvailability,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerReading,
    LightbarState,
    PlayerLedState,
    TriggerMode,
    TriggerState,
    normalize_controller_input,
)

LOGGER = get_logger(__name__)

SONY_VENDOR_ID = 0x054C
DUALSENSE_PRODUCT_IDS = (0x0CE6, 0x0DF2)
DUALSENSE_EDGE_PRODUCT_ID = 0x0DF2
_HID_OPEN_LOCK = threading.RLock()


class PyDualSenseFactory:
    """Connect through pydualsense while pinning one deterministic Windows HID path."""

    def __init__(self, *, platform: str | None = None) -> None:
        self.platform = platform or sys.platform
        self._preferred_hid_path: object | None = None

    @property
    def preferred_hid_path(self) -> object | None:
        return self._preferred_hid_path

    def connect(self) -> PyDualSenseAdapter:
        try:
            from pydualsense import pydualsense  # type: ignore[import-not-found,import-untyped]
            from pydualsense.enums import ConnectionType  # type: ignore[import-not-found,import-untyped]

            try:
                from pydualsense import TriggerModes  # type: ignore[import-not-found,import-untyped]
            except ImportError:
                TriggerModes = None
            try:
                from pydualsense import (  # type: ignore[import-not-found,import-untyped]
                    Brightness,
                    LedOptions,
                    PlayerID,
                    PulseOptions,
                )
            except ImportError:
                Brightness = LedOptions = PlayerID = PulseOptions = None
        except ImportError as exc:
            raise PlatformUnavailableError(
                "The pydualsense USB dependency is not installed.",
                detail=str(exc),
            ) from exc

        raw = None
        selected_hid_path: object | None = None
        try:
            if self.platform == "win32":
                raw, selected_hid_path = self._connect_windows_stable(pydualsense, ConnectionType)
            else:
                raw = pydualsense()
                raw.init()
        except Exception as exc:
            if raw is not None:
                _close_quietly(raw)
            raise ControllerUnavailableError("DualSense USB controller is not available.", detail=str(exc)) from exc
        if getattr(raw, "conType", None) != ConnectionType.USB:
            detected = getattr(getattr(raw, "conType", None), "name", str(getattr(raw, "conType", None)))
            _close_quietly(raw)
            raise ControllerUnavailableError(
                "DS5Forge P0 accepts DualSense controllers over USB only.",
                detail=f"Detected connection type: {detected}",
            )
        if selected_hid_path is not None:
            self._preferred_hid_path = selected_hid_path
            LOGGER.info(
                "DualSense HID path selected",
                extra={"event": "controller.hid_selected", "hid_path": _display_hid_path(selected_hid_path)},
            )
        return PyDualSenseAdapter(
            raw,
            trigger_modes=TriggerModes,
            brightness=Brightness,
            led_options=LedOptions,
            player_ids=PlayerID,
            pulse_options=PulseOptions,
        )

    def _connect_windows_stable(self, raw_type: Any, connection_type: Any) -> tuple[Any, object]:
        """Open one concrete HID path instead of pydualsense's VID/PID first-match behavior.

        pydualsense enumerates candidate devices but then reopens only by VID/PID,
        which is ambiguous when Windows exposes more than one DualSense. Keeping
        the last successful path first also prevents reconnects from bouncing
        between two present devices (including USB-over-IP presentations).
        """

        import hidapi  # type: ignore[import-not-found,import-untyped]

        try:
            from pydualsense import hidguardian  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            hidguardian = None
        if hidguardian is not None and bool(hidguardian.check_hide()):
            raise RuntimeError("HIDGuardian is hiding the DualSense from DS5Forge.")

        with _HID_OPEN_LOCK:
            candidates = _ordered_hid_candidates(
                list(hidapi.enumerate(vendor_id=SONY_VENDOR_ID)),
                preferred_path=self._preferred_hid_path,
            )
            if not candidates:
                raise RuntimeError("No DualSense HID interface is currently available.")

            failures: list[str] = []
            for candidate in candidates:
                path = getattr(candidate, "path", None)
                product_id = int(getattr(candidate, "product_id", 0) or 0)
                if path is None:
                    continue
                raw = raw_type()

                def open_selected(_raw: Any, *, _candidate: Any = candidate, _product_id: int = product_id):
                    return hidapi.Device(info=_candidate), _product_id == DUALSENSE_EDGE_PRODUCT_ID

                raw._pydualsense__find_device = MethodType(open_selected, raw)
                try:
                    raw.init()
                    # pydualsense does not consistently surface the HID identity
                    # it opened. Preserve the concrete DeviceInfo values so the
                    # core/UI can distinguish multiple attached DualSense units.
                    if getattr(raw, "serial", None) in {None, ""}:
                        raw.serial = getattr(candidate, "serial_number", None)
                    if getattr(raw, "vendor_id", None) is None:
                        raw.vendor_id = int(getattr(candidate, "vendor_id", 0) or 0) or None
                    if getattr(raw, "product_id", None) is None:
                        raw.product_id = product_id or None
                    if getattr(raw, "model", None) in {None, ""}:
                        raw.model = getattr(candidate, "product_string", None) or "DualSense"
                    if getattr(raw, "conType", None) != connection_type.USB:
                        detected = getattr(
                            getattr(raw, "conType", None),
                            "name",
                            str(getattr(raw, "conType", None)),
                        )
                        failures.append(f"{_display_hid_path(path)}: transport={detected}")
                        _close_quietly(raw)
                        continue
                    return raw, path
                except Exception as exc:
                    failures.append(f"{_display_hid_path(path)}: {exc}")
                    _close_quietly(raw)

        detail = "; ".join(failures[-4:]) or "all candidate HID paths failed"
        raise RuntimeError(f"No stable USB DualSense HID path could be opened: {detail}")


class PyDualSenseAdapter:
    def __init__(
        self,
        raw: Any,
        *,
        trigger_modes: Any = None,
        brightness: Any = None,
        led_options: Any = None,
        player_ids: Any = None,
        pulse_options: Any = None,
        report_stale_after: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.raw = raw
        self._monotonic = monotonic
        self._report_stale_after = max(0.25, float(report_stale_after))
        self._tracks_report_stream = hasattr(raw, "states")
        self._last_report_ref = getattr(raw, "states", None)
        self._last_report_at = self._monotonic()
        self._stale_report_logged = False
        self._trigger_modes = trigger_modes
        self._brightness = brightness
        self._led_options = led_options
        self._player_ids = player_ids
        self._pulse_options = pulse_options
        self._lightbar_state = LightbarState()
        self._player_led_state = PlayerLedState()
        light = getattr(raw, "light", None)
        self._player_led_pattern = getattr(light, "playerNumber", None)
        if self._player_led_pattern is None and player_ids is not None:
            self._player_led_pattern = getattr(player_ids, "PLAYER_1", None)
        self._trigger_state = TriggerState()
        self._exclusive_output_lock = threading.RLock()
        self._generated_output_suppression_owners: set[str] = set()
        self._normal_write_report = getattr(raw, "writeReport", None)
        self.identity = ControllerIdentity(
            model=str(getattr(raw, "model", "DualSense")),
            serial=_optional_string(getattr(raw, "serial", None)),
            vendor_id=_optional_int(getattr(raw, "vendor_id", None)),
            product_id=_optional_int(getattr(raw, "product_id", None)),
            transport="usb",
        )
        trigger_left = getattr(raw, "triggerL", None)
        trigger_right = getattr(raw, "triggerR", None)
        touch_state = getattr(raw, "state", None)
        availability = {
            "usb": CapabilityAvailability(True, True),
            "rumble": _availability(
                callable(getattr(raw, "setLeftMotor", None)) and callable(getattr(raw, "setRightMotor", None)),
                "The installed adapter does not expose both motor setters.",
            ),
            "touchpad": _availability(
                touch_state is not None
                and (hasattr(touch_state, "trackPadTouch0") or hasattr(touch_state, "trackPadTouch1")),
                "The installed adapter does not expose touchpad state.",
            ),
            "microphone_button": _availability(
                touch_state is not None and hasattr(touch_state, "micBtn"),
                "The installed adapter does not expose the microphone button state.",
            ),
            "lightbar": _availability(
                callable(getattr(light, "setColorI", None)),
                "The installed adapter does not expose lightbar color output.",
            ),
            "adaptive_triggers": _availability(
                _trigger_surface_available(trigger_left, trigger_right, trigger_modes),
                "The installed adapter does not expose typed adaptive-trigger controls.",
            ),
            "adaptive_trigger_output_reports": _availability(
                callable(getattr(raw, "prepareReport", None)) and callable(getattr(raw, "writeReport", None)),
                "The pinned adapter exposes trigger setters but no proven output-report passthrough.",
            ),
        }
        self.capabilities = ControllerCapabilities(
            usb=True,
            rumble=availability["rumble"].enabled,
            touchpad=availability["touchpad"].enabled,
            microphone_button=availability["microphone_button"].enabled,
            lightbar=availability["lightbar"].enabled,
            adaptive_triggers=availability["adaptive_triggers"].enabled,
            adaptive_trigger_output_reports=availability["adaptive_trigger_output_reports"].enabled,
            availability=availability,
        )

    def is_connected(self) -> bool:
        if not bool(getattr(self.raw, "connected", True)):
            return False
        if getattr(self.raw, "ds_thread", True) is False:
            return False
        report_thread = getattr(self.raw, "report_thread", None)
        is_alive = getattr(report_thread, "is_alive", None)
        if callable(is_alive) and not bool(is_alive()):
            LOGGER.warning(
                "pydualsense report thread stopped while connected flag remained set",
                extra={"event": "controller.report_thread_dead"},
            )
            return False
        if self._tracks_report_stream:
            now = self._monotonic()
            report_ref = getattr(self.raw, "states", None)
            if report_ref is not None and report_ref is not self._last_report_ref:
                self._last_report_ref = report_ref
                self._last_report_at = now
                self._stale_report_logged = False
            elif now - self._last_report_at >= self._report_stale_after:
                if not self._stale_report_logged:
                    LOGGER.warning(
                        "pydualsense input report stream stalled while transport still appeared connected",
                        extra={
                            "event": "controller.report_stream_stalled",
                            "stale_seconds": round(now - self._last_report_at, 3),
                        },
                    )
                    self._stale_report_logged = True
                return False
        return True

    def read(self) -> ControllerReading:
        if not self.is_connected():
            return ControllerReading(connected=False)
        try:
            state = getattr(self.raw, "state", None)
            if state is None:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_READ_FAILED,
                    "Controller state is unavailable.",
                )
            battery_value = getattr(getattr(self.raw, "battery", None), "Level", 0)
            return ControllerReading(
                connected=True,
                battery=BatterySnapshot(
                    level=_optional_int(battery_value) or 0,
                    charging=_optional_bool(getattr(getattr(self.raw, "battery", None), "Charging", None)),
                ),
                input=normalize_controller_input(state),
                timestamp=time.time(),
            )
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_READ_FAILED,
                "Controller input could not be read.",
                detail=str(exc),
            ) from exc

    def set_motors(self, left: int, right: int) -> None:
        left, right = _motor_value(left), _motor_value(right)
        try:
            self.raw.setLeftMotor(left)
            self.raw.setRightMotor(right)
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_OUTPUT_FAILED,
                "Controller rumble output failed.",
                detail=str(exc),
            ) from exc

    def exclusive_output_passthrough_available(self) -> bool:
        return bool(
            self.identity.transport == "usb"
            and callable(self._normal_write_report)
            and callable(getattr(self.raw, "prepareReport", None))
        )

    def begin_exclusive_output_passthrough(self) -> None:
        """Stop pydualsense from racing game-authored virtual DualSense reports."""

        self._begin_generated_output_suppression("exclusive")

    def begin_native_game_output_passthrough(self) -> None:
        """Let a native DualSense-aware game own physical controller output.

        pydualsense normally writes a synthesized output report after every
        input read. In native game mode that races the game's own USB DualSense
        output and can overwrite haptics, LEDs and adaptive-trigger packets.
        Input reads remain active; only DS5Forge's generated writes are muted.
        """

        self._begin_generated_output_suppression("native_game")

    def _begin_generated_output_suppression(self, owner: str) -> None:
        with self._exclusive_output_lock:
            if owner in self._generated_output_suppression_owners:
                return
            if not self.exclusive_output_passthrough_available():
                raise CapabilityUnavailableError(
                    "controller_output_passthrough",
                    "The connected USB adapter does not expose safe native output passthrough.",
                )

            if not self._generated_output_suppression_owners:

                def suppress_generated_write(_raw: Any, _report: Any) -> None:
                    return None

                self.raw.writeReport = MethodType(suppress_generated_write, self.raw)
            self._generated_output_suppression_owners.add(owner)

    def write_exclusive_output_report(self, report: bytes) -> None:
        with self._exclusive_output_lock:
            if "exclusive" not in self._generated_output_suppression_owners:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_OUTPUT_FAILED,
                    "Exclusive output passthrough is not active.",
                )
            payload = bytes(report)
            if len(payload) != 64 or payload[0] != 0x02:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_OUTPUT_FAILED,
                    "Exclusive provider returned an invalid USB DualSense output report.",
                    detail=f"expected 64-byte report 0x02, got length={len(payload)} id={payload[0] if payload else None}",
                )
            writer = self._normal_write_report
            if not callable(writer):
                raise CapabilityUnavailableError(
                    "exclusive_output_passthrough",
                    "The connected adapter lost its raw output-report writer.",
                )
            try:
                writer(list(payload))
            except Exception as exc:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_OUTPUT_FAILED,
                    "Exclusive output report could not be forwarded to the physical DualSense.",
                    detail=str(exc),
                ) from exc

    def end_exclusive_output_passthrough(self) -> None:
        self._end_generated_output_suppression("exclusive")

    def end_native_game_output_passthrough(self) -> None:
        self._end_generated_output_suppression("native_game")

    def _end_generated_output_suppression(self, owner: str) -> None:
        with self._exclusive_output_lock:
            if owner not in self._generated_output_suppression_owners:
                return
            self._generated_output_suppression_owners.discard(owner)
            if self._generated_output_suppression_owners:
                return
            writer = self._normal_write_report
            if callable(writer):
                self.raw.writeReport = writer
        # Re-apply DS5Forge's normal output state only after the final
        # passthrough owner releases the channel. This is best-effort because
        # teardown must never strand controller input solely due to an output
        # restoration failure.
        try:
            prepare = getattr(self.raw, "prepareReport", None)
            if callable(writer) and callable(prepare):
                writer(prepare())
        except Exception:
            LOGGER.exception(
                "normal controller output could not be restored after passthrough",
                extra={"event": "controller.output_passthrough_restore", "owner": owner},
            )

    def neutralize(self) -> None:
        try:
            self.set_motors(0, 0)
        except DS5ForgeError:
            LOGGER.exception("controller neutralization failed", extra={"event": "controller.neutralize"})
        try:
            self.reset_triggers()
        except DS5ForgeError:
            LOGGER.exception("trigger neutralization failed", extra={"event": "controller.trigger_neutralize"})
        try:
            self.reset_player_leds()
        except DS5ForgeError:
            LOGGER.exception("Player LED neutralization failed", extra={"event": "controller.player_led_neutralize"})

    def get_lightbar(self) -> LightbarState:
        capability = self.capabilities.capability("lightbar")
        if not capability.enabled:
            raise CapabilityUnavailableError("lightbar", capability.reason)
        # pydualsense exposes one shared LED update mask.  Reading that mask
        # cannot tell whether DS5Forge intentionally disabled only the RGB
        # strip or only the player LEDs, so the adapter's last successfully
        # applied command is the authoritative state.
        return self._lightbar_state

    def set_lightbar(self, state: LightbarState) -> None:
        capability = self.capabilities.capability("lightbar")
        if not capability.enabled:
            raise CapabilityUnavailableError("lightbar", capability.reason)
        try:
            self._apply_lighting_state(state, self._player_led_state)
            self._lightbar_state = state
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.LIGHTBAR_OUTPUT_FAILED,
                "Lightbar output failed.",
                detail=str(exc),
            ) from exc

    def reset_lightbar(self) -> None:
        self.set_lightbar(LightbarState())

    def get_player_leds(self) -> PlayerLedState:
        return self._player_led_state

    def set_player_leds(self, state: PlayerLedState) -> None:
        try:
            self._apply_lighting_state(self._lightbar_state, state)
            self._player_led_state = state
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.LIGHTBAR_OUTPUT_FAILED,
                "Player LED output failed.",
                detail=str(exc),
            ) from exc

    def reset_player_leds(self) -> None:
        self.set_player_leds(PlayerLedState())

    def _apply_lighting_state(self, lightbar: LightbarState, player_leds: PlayerLedState) -> None:
        """Apply RGB + player LEDs as one pydualsense lighting transaction.

        ``LedOptions`` is a validity bitmask, not independent on/off state for
        the two surfaces.  Always reconciling both fields with ``Both`` avoids
        a later RGB write re-enabling player LEDs (or a player-LED write
        suppressing the RGB strip).  Actual on/off state is represented by
        zero RGB and a zero PlayerID pattern respectively.
        """

        light = self.raw.light
        light.setColorI(*lightbar.scaled_rgb)
        _set_light_pulse(light, self._pulse_options, lightbar.pulse)

        brightness = 0 if player_leds.intensity >= 0.75 else 1 if player_leds.intensity >= 0.35 else 2
        _set_light_brightness(light, self._brightness, brightness)
        self._set_player_led_enabled(light, player_leds.enabled)

        # pydualsense 0.7.x uses this mask to say which LED fields in the
        # output report are valid.  ``Off`` means no LED-field update, so it
        # must not be used to represent a desired disabled state.
        _set_light_option(light, self._led_options, "Both")

    def _set_player_led_enabled(self, light: Any, enabled: bool) -> None:
        setter = getattr(light, "setPlayerID", None)
        enum_type = self._player_ids
        if not callable(setter) or enum_type is None:
            if enabled:
                return
            raise CapabilityUnavailableError(
                "lightbar", "The installed adapter does not expose Player LED enable control."
            )
        if enabled:
            pattern = self._player_led_pattern or getattr(enum_type, "PLAYER_1", None)
            if pattern is None:
                raise CapabilityUnavailableError(
                    "lightbar", "The installed adapter does not expose a Player LED pattern."
                )
            setter(pattern)
            return
        try:
            setter(enum_type(0))
        except (TypeError, ValueError) as exc:
            raise CapabilityUnavailableError(
                "lightbar", "The installed adapter cannot represent disabled Player LEDs."
            ) from exc

    def set_triggers(self, state: TriggerState) -> None:
        capability = self.capabilities.capability("adaptive_triggers")
        if not capability.enabled:
            raise CapabilityUnavailableError("adaptive_triggers", capability.reason)
        try:
            _set_trigger(self.raw.triggerL, state.left, self._trigger_modes)
            _set_trigger(self.raw.triggerR, state.right, self._trigger_modes)
            self._trigger_state = state
        except DS5ForgeError:
            self._reset_triggers_best_effort()
            raise
        except Exception as exc:
            self._reset_triggers_best_effort()
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED,
                "Adaptive-trigger output failed.",
                detail=str(exc),
            ) from exc

    def set_trigger_effect(self, trigger: str, effect: AdaptiveTriggerEffect) -> None:
        current = self._trigger_state
        if trigger == "left":
            self.set_triggers(TriggerState(left=effect, right=current.right))
        elif trigger == "right":
            self.set_triggers(TriggerState(left=current.left, right=effect))
        else:
            raise DS5ForgeError(ErrorCode.API_VALIDATION, "Trigger must be left or right.")

    def reset_triggers(self) -> None:
        capability = self.capabilities.capability("adaptive_triggers")
        if not capability.enabled:
            return
        try:
            _set_trigger(self.raw.triggerL, AdaptiveTriggerEffect(), self._trigger_modes)
            _set_trigger(self.raw.triggerR, AdaptiveTriggerEffect(), self._trigger_modes)
            self._trigger_state = TriggerState()
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED,
                "Adaptive triggers could not be reset.",
                detail=str(exc),
            ) from exc

    reset_trigger_effects = reset_triggers

    def _reset_triggers_best_effort(self) -> None:
        try:
            self.reset_triggers()
        except DS5ForgeError:
            LOGGER.exception("trigger reset after output failure failed", extra={"event": "controller.trigger_reset"})

    def startup_feedback(self) -> None:
        """Preserve the upstream lightbar/pulse cue without changing tuning."""

        try:
            if self.capabilities.capability("lightbar").enabled:
                self.set_lightbar(LightbarState(0, 80, 255))
            for _ in range(2):
                self.set_motors(100, 0)
                time.sleep(0.15)
                self.set_motors(0, 0)
                time.sleep(0.1)
        except DS5ForgeError:
            LOGGER.exception("controller startup feedback failed", extra={"event": "controller.startup_feedback"})
        except Exception:
            LOGGER.exception("controller startup feedback failed", extra={"event": "controller.startup_feedback"})

    def close(self) -> None:
        try:
            self.end_exclusive_output_passthrough()
            self.end_native_game_output_passthrough()
        except Exception:
            LOGGER.exception(
                "output passthrough cleanup failed during controller close",
                extra={"event": "controller.output_passthrough_close"},
            )
        try:
            self.raw.close()
        except Exception as exc:
            LOGGER.warning("controller close failed", extra={"event": "controller.close", "error": str(exc)})


def _availability(enabled: bool, reason: str) -> CapabilityAvailability:
    return CapabilityAvailability(supported=enabled, available=enabled, reason=None if enabled else reason)


def _trigger_surface_available(left: Any, right: Any, modes: Any) -> bool:
    return bool(
        left is not None
        and right is not None
        and callable(getattr(left, "setMode", None))
        and callable(getattr(left, "setForce", None))
        and callable(getattr(right, "setMode", None))
        and callable(getattr(right, "setForce", None))
        and modes is not None
        and getattr(modes, "Off", None) is not None
        and getattr(modes, "Rigid", None) is not None
        and getattr(modes, "Rigid_A", None) is not None
        and _pulse_mode(modes) is not None
    )


def _trigger_mode(modes: Any, effect: AdaptiveTriggerEffect) -> Any:
    if modes is None:
        raise RuntimeError("trigger mode enum is unavailable")
    names = {
        TriggerMode.OFF.value: ("Off",),
        TriggerMode.RIGID.value: ("Rigid",),
        # pydualsense 0.7.5 exposes Rigid_A as 0x21, the documented
        # zone-based feedback effect.  Unlike legacy Rigid (0x01), it has
        # discrete 1..8 strength levels and can be turned fully off.
        TriggerMode.RESISTANCE.value: ("Rigid_A",),
        TriggerMode.PULSE.value: ("Pulse_AB", "PulseAB", "Pulse"),
    }
    for name in names.get(effect.mode, ("Off",)):
        candidate = getattr(modes, name, None)
        if candidate is not None:
            return candidate
    raise ValueError(f"unsupported trigger mode: {effect.mode}")


def _set_trigger(raw_trigger: Any, effect: AdaptiveTriggerEffect, modes: Any = None) -> None:
    # ``modes`` is attached by the adapter caller through the temporary
    # attribute below; keeping this helper library-agnostic makes it easy to
    # test with a small fake trigger object.
    trigger_modes = modes or getattr(raw_trigger, "_ds5forge_modes", None)
    raw_trigger.setMode(_trigger_mode(trigger_modes, effect))
    if effect.is_off:
        forces = (0, 0, 0, 0, 0, 0, 0)
    elif effect.mode == TriggerMode.RESISTANCE.value:
        if effect.force <= 0:
            raw_trigger.setMode(_trigger_mode(trigger_modes, AdaptiveTriggerEffect()))
            forces = (0, 0, 0, 0, 0, 0, 0)
        else:
            forces = _feedback_forces(effect)
    elif effect.mode == TriggerMode.RIGID.value:
        # Legacy 0x01 continuous resistance: P0=start position, P1=force.
        forces = (effect.start_position, effect.force, 0, 0, 0, 0, 0)
    else:
        forces = (effect.start_position, effect.force, effect.end_position, effect.amplitude, effect.frequency, 0, 0)
    for index, force in enumerate(forces):
        raw_trigger.setForce(index, force)


def _feedback_forces(effect: AdaptiveTriggerEffect) -> tuple[int, int, int, int, int, int, int]:
    """Encode DualSense feedback mode (0x21) into pydualsense's seven slots.

    The effect uses ten trigger-travel zones.  Slots 0..1 contain the active
    zone bitmask, slots 2..5 pack the 3-bit strength for every zone, and slot
    6 is the frequency byte (zero for constant resistance).
    """

    start_zone = max(0, min(9, round(effect.start_position * 9 / 255)))
    strength = max(1, min(8, round(effect.force * 8 / 255)))
    active_zones = 0
    packed_strength = 0
    encoded_strength = (strength - 1) & 0x07
    for zone in range(start_zone, 10):
        active_zones |= 1 << zone
        packed_strength |= encoded_strength << (3 * zone)
    return (
        active_zones & 0xFF,
        (active_zones >> 8) & 0xFF,
        packed_strength & 0xFF,
        (packed_strength >> 8) & 0xFF,
        (packed_strength >> 16) & 0xFF,
        (packed_strength >> 24) & 0xFF,
        0,
    )


def _reset_trigger(raw_trigger: Any, modes: Any) -> None:
    _set_trigger(raw_trigger, AdaptiveTriggerEffect(), modes)


def _motor_value(value: int) -> int:
    return max(0, min(255, int(value)))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pulse_mode(modes: Any) -> Any:
    return next(
        (
            getattr(modes, name, None)
            for name in ("Pulse_AB", "PulseAB", "Pulse")
            if getattr(modes, name, None) is not None
        ),
        None,
    )


def _set_light_option(light: Any, enum_type: Any, name: str) -> None:
    setter = getattr(light, "setLEDOption", None)
    option = getattr(enum_type, name, None) if enum_type is not None else None
    if option is None and name == "Player" and enum_type is not None:
        option = getattr(enum_type, "Player", getattr(enum_type, "PlayerOnly", None))
    if not callable(setter) or option is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose LED enable control.")
    setter(option)


def _set_light_brightness(light: Any, enum_type: Any, value: int) -> None:
    setter = getattr(light, "setBrightness", None)
    if not callable(setter):
        if value == 2:
            return
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose brightness control.")
    if enum_type is None and value == 2:
        return
    names = {0: "high", 1: "medium", 2: "low"}
    brightness = getattr(enum_type, names.get(value, ""), None) if enum_type is not None else None
    if brightness is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose this brightness level.")
    setter(brightness)


def _set_light_pulse(light: Any, enum_type: Any, value: str) -> None:
    setter = getattr(light, "setPulseOption", None)
    if not callable(setter):
        if value == "off":
            return
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose pulse control.")
    if enum_type is None and value == "off":
        return
    names = {"off": "Off", "slow": "FadeBlue", "fast": "FadeOut"}
    pulse = getattr(enum_type, names.get(value, ""), None) if enum_type is not None else None
    if pulse is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose this pulse mode.")
    setter(pulse)


def _light_enabled(value: Any, enum_type: Any) -> bool:
    off = getattr(enum_type, "Off", None) if enum_type is not None else None
    return value != off if off is not None and value is not None else True


def _light_brightness(value: Any, enum_type: Any) -> int:
    raw = getattr(value, "value", value)
    if isinstance(raw, int):
        return max(0, min(2, raw))
    for number, name in ((0, "high"), (1, "medium"), (2, "low")):
        if value == getattr(enum_type, name, object()):
            return number
    return 2


def _light_pulse(value: Any, enum_type: Any) -> str:
    for name, label in (("Off", "off"), ("FadeBlue", "slow"), ("FadeOut", "fast")):
        if value == getattr(enum_type, name, object()):
            return label
    return "off"


def _ordered_hid_candidates(devices: list[Any], *, preferred_path: object | None) -> list[Any]:
    candidates = [
        device
        for device in devices
        if int(getattr(device, "vendor_id", 0) or 0) == SONY_VENDOR_ID
        and int(getattr(device, "product_id", 0) or 0) in DUALSENSE_PRODUCT_IDS
        and getattr(device, "path", None) is not None
    ]

    def sort_key(device: Any) -> tuple[int, int, str]:
        path = getattr(device, "path", None)
        preferred = 0 if preferred_path is not None and path == preferred_path else 1
        # USB DualSense exposes the gamepad on interface 3 on Windows. Prefer
        # that concrete HID interface before other Sony HID presentations.
        interface = 0 if int(getattr(device, "interface_number", -1) or -1) == 3 else 1
        return preferred, interface, _display_hid_path(path).casefold()

    return sorted(candidates, key=sort_key)


def _display_hid_path(path: object) -> str:
    if isinstance(path, bytes):
        return path.decode("utf-8", errors="replace")
    return str(path)


def _close_quietly(raw: Any) -> None:
    try:
        raw.close()
    except Exception:
        LOGGER.debug("failed to close unsuccessful controller adapter", exc_info=True)
