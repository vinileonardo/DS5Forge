"""Deterministic USB controller lifecycle owner."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..diagnostics.logging import get_logger
from ..domain.errors import CapabilityUnavailableError, ControllerUnavailableError, DS5ForgeError, ErrorCode
from ..domain.models import ConnectionState, ControllerReading, LightbarState, PlayerLedState, TriggerState
from .ports import ControllerAdapter, ControllerFactory

LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LifecycleNotification:
    state: ConnectionState
    error: DS5ForgeError | None = None


class ControllerService:
    """Single owner for discovery, reads, output and teardown.

    The service deliberately has no alternate-transport discovery path. A
    factory is injected so lifecycle tests can use a deterministic fake adapter.
    """

    def __init__(
        self,
        factory: ControllerFactory,
        *,
        on_lifecycle: Callable[[LifecycleNotification], None] | None = None,
        on_connected: Callable[[ControllerAdapter], None] | None = None,
        on_disconnected: Callable[[], None] | None = None,
        on_reading: Callable[[ControllerReading], None] | None = None,
        on_motors: Callable[[int, int], None] | None = None,
        min_backoff: float = 0.25,
        max_backoff: float = 4.0,
        poll_interval: float = 1.0 / 250.0,
    ) -> None:
        self.factory = factory
        self.on_lifecycle = on_lifecycle
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_reading = on_reading
        self.on_motors = on_motors
        self.min_backoff = max(0.01, min_backoff)
        self.max_backoff = max(self.min_backoff, max_backoff)
        self.poll_interval = max(0.001, poll_interval)
        self.stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._adapter: ControllerAdapter | None = None
        self._adapter_lock = threading.RLock()
        self._pulse_thread: threading.Thread | None = None
        self._pulse_stop = threading.Event()
        self._started = False

    @property
    def adapter(self) -> ControllerAdapter | None:
        # Internal services may inspect capabilities; presentation code never
        # receives this object.
        with self._adapter_lock:
            return self._adapter

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.alive:
            return
        self.stop_event.clear()
        self._started = True
        self._thread = threading.Thread(target=self._run, name="DS5ForgeController", daemon=False)
        self._thread.start()

    def stop(self, *, join_timeout: float = 5.0) -> None:
        self.stop_event.set()
        self._pulse_stop.set()
        self._transition(ConnectionState.STOPPING)
        adapter = self.adapter
        if adapter is not None:
            self._neutralize(adapter)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)
        pulse = self._pulse_thread
        if pulse is not None and pulse is not threading.current_thread():
            pulse.join(timeout=join_timeout)
        if self.alive:
            LOGGER.error("controller service did not stop before timeout", extra={"event": "controller.stop_timeout"})

    def set_motors(self, left: int, right: int) -> bool:
        adapter = self.adapter
        if adapter is None:
            return False
        try:
            adapter.set_motors(left, right)
            if self.on_motors:
                self.on_motors(left, right)
            return True
        except DS5ForgeError as exc:
            LOGGER.warning("motor output failed", extra={"event": "controller.output", "error_code": exc.code.value})
            return False
        except Exception:
            LOGGER.exception("unexpected motor output failure", extra={"event": "controller.output"})
            return False

    def neutralize(self) -> None:
        adapter = self.adapter
        if adapter is not None:
            self._neutralize(adapter)
        if self.on_motors:
            self.on_motors(0, 0)

    def neutralize_motors(self) -> None:
        """Stop rumble without touching adaptive-trigger output.

        Rumble-only operations (muting audio rumble, finishing a haptics bench)
        must not clobber a user's adaptive-trigger configuration. Full
        neutralization stays reserved for disconnect and teardown paths.
        """

        if self.adapter is None:
            return
        if not self.set_motors(0, 0):
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_OUTPUT_FAILED,
                "Motor output could not be neutralized.",
            )

    def get_lightbar(self) -> LightbarState:
        adapter = self._require_adapter("lightbar")
        getter = getattr(adapter, "get_lightbar", None)
        if not callable(getter):
            raise CapabilityUnavailableError("lightbar", "The connected adapter does not expose lightbar state.")
        try:
            value = getter()
            return value if isinstance(value, LightbarState) else LightbarState()
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Lightbar state could not be read.", detail=str(exc)
            ) from exc

    def set_lightbar(self, state: LightbarState) -> None:
        adapter = self._require_adapter("lightbar")
        setter = getattr(adapter, "set_lightbar", None)
        if not callable(setter):
            raise CapabilityUnavailableError("lightbar", "The connected adapter does not expose lightbar output.")
        try:
            setter(state)
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Lightbar output failed.", detail=str(exc)) from exc

    def reset_lightbar(self) -> None:
        adapter = self._require_adapter("lightbar")
        resetter = getattr(adapter, "reset_lightbar", None)
        if callable(resetter):
            try:
                resetter()
                return
            except DS5ForgeError:
                raise
            except Exception as exc:
                raise DS5ForgeError(
                    ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Lightbar reset failed.", detail=str(exc)
                ) from exc
        self.set_lightbar(LightbarState())

    def get_player_leds(self) -> PlayerLedState:
        adapter = self._require_adapter("lightbar")
        getter = getattr(adapter, "get_player_leds", None)
        if not callable(getter):
            raise CapabilityUnavailableError("lightbar", "The connected adapter does not expose Player LED state.")
        try:
            value = getter()
            return value if isinstance(value, PlayerLedState) else PlayerLedState()
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Player LED state could not be read.", detail=str(exc)
            ) from exc

    def set_player_leds(self, state: PlayerLedState) -> None:
        adapter = self._require_adapter("lightbar")
        setter = getattr(adapter, "set_player_leds", None)
        if not callable(setter):
            raise CapabilityUnavailableError("lightbar", "The connected adapter does not expose Player LED output.")
        try:
            setter(state)
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Player LED output failed.", detail=str(exc)) from exc

    def reset_player_leds(self) -> None:
        adapter = self._require_adapter("lightbar")
        resetter = getattr(adapter, "reset_player_leds", None)
        if callable(resetter):
            try:
                resetter()
                return
            except DS5ForgeError:
                raise
            except Exception as exc:
                raise DS5ForgeError(
                    ErrorCode.LIGHTBAR_OUTPUT_FAILED, "Player LED reset failed.", detail=str(exc)
                ) from exc
        self.set_player_leds(PlayerLedState())

    def set_triggers(self, state: TriggerState) -> None:
        adapter = self._require_adapter("adaptive_triggers")
        setter = getattr(adapter, "set_triggers", None)
        if not callable(setter):
            raise CapabilityUnavailableError(
                "adaptive_triggers", "The connected adapter does not expose adaptive-trigger output."
            )
        try:
            setter(state)
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED, "Adaptive-trigger output failed.", detail=str(exc)
            ) from exc

    def reset_triggers(self) -> None:
        adapter = self._require_adapter("adaptive_triggers")
        resetter = getattr(adapter, "reset_triggers", None)
        if not callable(resetter):
            raise CapabilityUnavailableError(
                "adaptive_triggers", "The connected adapter does not expose adaptive-trigger reset output."
            )
        try:
            resetter()
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED, "Adaptive triggers could not be reset.", detail=str(exc)
            ) from exc

    def _require_adapter(self, capability: str) -> ControllerAdapter:
        adapter = self.adapter
        if adapter is None:
            raise ControllerUnavailableError()
        capabilities = getattr(adapter, "capabilities", None)
        if capabilities is not None:
            availability = getattr(capabilities, "availability", {}).get(capability)
            supported = bool(getattr(capabilities, capability, False))
            if availability is not None:
                supported = bool(getattr(availability, "enabled", supported))
            if not supported:
                reason = getattr(availability, "reason", None)
                raise CapabilityUnavailableError(capability, reason)
        return adapter

    def pulse(self, left: int = 200, right: int = 160, duration: float = 0.35) -> bool:
        if self.adapter is None:
            return False
        self._pulse_stop.set()
        previous = self._pulse_thread
        if previous is not None and previous is not threading.current_thread():
            previous.join(timeout=0.5)
        self._pulse_stop = threading.Event()
        stop = self._pulse_stop

        def run() -> None:
            if not self.set_motors(left, right):
                return
            stop.wait(max(0.01, duration))
            self.set_motors(0, 0)

        self._pulse_thread = threading.Thread(target=run, name="DS5ForgeRumblePulse", daemon=False)
        self._pulse_thread.start()
        return True

    def _run(self) -> None:
        backoff = self.min_backoff
        self._transition(ConnectionState.DISCONNECTED)
        while not self.stop_event.is_set():
            self._transition(ConnectionState.CONNECTING)
            try:
                adapter = self.factory.connect()
            except ControllerUnavailableError as exc:
                self._transition(ConnectionState.DISCONNECTED, exc)
                self._wait(backoff)
                backoff = min(self.max_backoff, backoff * 2)
                continue
            except DS5ForgeError as exc:
                # Platform/dependency failures are recoverable, but surfaced
                # as error instead of being silently swallowed.
                self._transition(ConnectionState.ERROR, exc)
                self._wait(backoff)
                backoff = min(self.max_backoff, backoff * 2)
                continue
            except Exception as exc:
                wrapped = DS5ForgeError(
                    ErrorCode.CONTROLLER_CONNECT_FAILED,
                    "Controller connection attempt failed.",
                    detail=str(exc),
                )
                LOGGER.exception("unexpected controller connection failure", extra={"event": "controller.connect"})
                self._transition(ConnectionState.ERROR, wrapped)
                self._wait(backoff)
                backoff = min(self.max_backoff, backoff * 2)
                continue

            backoff = self.min_backoff
            with self._adapter_lock:
                self._adapter = adapter
            # Preserve the upstream ordering: startup feedback runs before
            # haptics/touch services begin using the adapter, avoiding motor
            # races during the connection cue.
            try:
                adapter.startup_feedback()
            except Exception:
                LOGGER.exception("controller startup feedback failed", extra={"event": "controller.startup_feedback"})

            connected_ready = True
            try:
                if self.on_connected:
                    self.on_connected(adapter)
            except Exception as exc:
                wrapped = DS5ForgeError(
                    ErrorCode.INTERNAL,
                    "Controller services could not start.",
                    detail=str(exc),
                )
                LOGGER.exception("connected callback failed", extra={"event": "controller.connected_callback"})
                self._transition(ConnectionState.ERROR, wrapped)
                connected_ready = False
            if not connected_ready:
                try:
                    if self.on_disconnected:
                        self.on_disconnected()
                except Exception:
                    LOGGER.exception(
                        "disconnect cleanup failed after connected callback error",
                        extra={"event": "controller.disconnected_callback"},
                    )
                self._neutralize(adapter)
                try:
                    adapter.close()
                except Exception:
                    LOGGER.exception(
                        "controller close failed after callback error", extra={"event": "controller.close"}
                    )
                with self._adapter_lock:
                    if self._adapter is adapter:
                        self._adapter = None
                self._wait(backoff)
                backoff = min(self.max_backoff, backoff * 2)
                continue
            self._transition(ConnectionState.CONNECTED)

            lost = False
            while not self.stop_event.is_set():
                try:
                    if not adapter.is_connected():
                        lost = True
                        break
                    reading = adapter.read()
                    if not reading.connected:
                        lost = True
                        break
                    if self.on_reading:
                        self.on_reading(reading)
                except DS5ForgeError as exc:
                    LOGGER.warning(
                        "controller read failed",
                        extra={"event": "controller.read", "error_code": exc.code.value},
                    )
                    self._transition(ConnectionState.ERROR, exc)
                    lost = True
                    break
                except Exception as exc:
                    wrapped = DS5ForgeError(
                        ErrorCode.CONTROLLER_READ_FAILED,
                        "Controller input read failed.",
                        detail=str(exc),
                    )
                    LOGGER.exception("unexpected controller read failure", extra={"event": "controller.read"})
                    self._transition(ConnectionState.ERROR, wrapped)
                    lost = True
                    break
                self._wait(self.poll_interval)

            self._neutralize(adapter)
            try:
                if self.on_disconnected:
                    self.on_disconnected()
            except Exception:
                LOGGER.exception("disconnected callback failed", extra={"event": "controller.disconnected_callback"})
            with self._adapter_lock:
                if self._adapter is adapter:
                    self._adapter = None
            try:
                adapter.close()
            except Exception:
                LOGGER.exception("controller close failed", extra={"event": "controller.close"})

            if self.stop_event.is_set():
                break
            if lost:
                self._transition(ConnectionState.RECONNECTING)
                self._wait(backoff)
                backoff = min(self.max_backoff, backoff * 2)

        self.neutralize()
        self._transition(ConnectionState.DISCONNECTED)

    def _transition(self, state: ConnectionState, error: DS5ForgeError | None = None) -> None:
        if self.on_lifecycle:
            try:
                self.on_lifecycle(LifecycleNotification(state, error))
            except Exception:
                LOGGER.exception("lifecycle callback failed", extra={"event": "controller.lifecycle_callback"})

    def _wait(self, seconds: float) -> None:
        # Keep the configured USB read cadence (P2 uses approximately 250 Hz)
        # while still avoiding a zero-duration busy loop for malformed values.
        self.stop_event.wait(max(0.001, seconds))

    @staticmethod
    def _neutralize(adapter: ControllerAdapter) -> None:
        try:
            adapter.neutralize()
        except Exception:
            LOGGER.exception("controller neutralization failed", extra={"event": "controller.neutralize"})
