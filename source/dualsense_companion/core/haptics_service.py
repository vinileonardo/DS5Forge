"""Audio-to-rumble service using pure DSP and replaceable I/O ports."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from .dsp import Biquad, EnvelopeFollower, map_rumble_level, pcm_float32
from .ports import AudioCapture, AudioCaptureFactory

LOGGER = get_logger(__name__)


class HapticsService(threading.Thread):
    CHUNK_MS = 10
    DEVICE_CHECK_SECONDS = 2.0

    def __init__(
        self,
        motor_output: Callable[[int, int], bool],
        config_provider: Callable[[], dict],
        enabled_provider: Callable[[], bool],
        *,
        capture_factory: AudioCaptureFactory | None = None,
        reload_event: threading.Event | None = None,
        on_motors: Callable[[int, int], None] | None = None,
        on_audio: Callable[[str, str | None, str | None], None] | None = None,
        on_envelope: Callable[[float], None] | None = None,
        on_error: Callable[[DS5ForgeError], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(name="DS5ForgeHaptics", daemon=False)
        self.motor_output = motor_output
        self.config_provider = config_provider
        self.enabled_provider = enabled_provider
        self.capture_factory = capture_factory
        self.reload_event = reload_event or threading.Event()
        self.on_motors = on_motors
        self.on_audio = on_audio
        self.on_envelope = on_envelope
        self.on_error = on_error
        self.clock = clock
        self.stop_event = threading.Event()
        self._capture_lock = threading.RLock()
        self._active_capture: AudioCapture | None = None
        self.last_left = -1
        self.last_right = -1

    def stop(self, *, join_timeout: float = 3.0) -> None:
        self.stop_event.set()
        # WASAPI reads can block beyond the nominal chunk interval on device
        # changes/teardown. Close the active capture from the caller thread so
        # PortAudio wakes the worker instead of leaving a non-daemon thread
        # alive and preventing the packaged sidecar from exiting.
        with self._capture_lock:
            capture = self._active_capture
        if capture is not None:
            try:
                capture.close()
            except Exception:
                LOGGER.debug("active audio capture close during stop failed", exc_info=True)
        self._set_motors(0, 0)
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=join_timeout)
        if self.is_alive():
            LOGGER.error("haptics service did not stop before timeout", extra={"event": "audio.stop_timeout"})

    def run(self) -> None:
        if self.capture_factory is None:
            error = DS5ForgeError(
                ErrorCode.AUDIO_UNAVAILABLE,
                "No audio capture adapter is configured.",
            )
            self._report_error(error)
            if self.on_audio:
                self.on_audio("error", None, error.message)
            return
        while not self.stop_event.is_set():
            try:
                self._run_once()
            except DS5ForgeError as exc:
                if self.stop_event.is_set():
                    break
                self._report_error(exc)
                self._set_motors(0, 0)
                if self.on_audio:
                    self.on_audio("error", None, exc.message)
                self.stop_event.wait(2.0)
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                wrapped = DS5ForgeError(ErrorCode.AUDIO_CAPTURE_FAILED, "Audio haptics worker failed.", detail=str(exc))
                LOGGER.exception("unexpected haptics worker failure", extra={"event": "audio.worker"})
                self._report_error(wrapped)
                self._set_motors(0, 0)
                if self.on_audio:
                    self.on_audio("error", None, wrapped.message)
                self.stop_event.wait(2.0)
        self._set_motors(0, 0)
        if self.on_audio:
            self.on_audio("stopped", None, None)

    def _run_once(self) -> None:
        assert self.capture_factory is not None
        with self.capture_factory.open() as capture:
            with self._capture_lock:
                self._active_capture = capture
            try:
                if self.on_audio:
                    self.on_audio("listening", capture.name, None)
                config = self.config_provider()
                rate = capture.sample_rate
                lp = Biquad.lowpass(rate, config["heavy_cutoff_hz"])
                bp = Biquad.bandpass(rate, config["texture_center_hz"])
                fast_l = EnvelopeFollower(config["fast_attack_ms"], config["fast_release_ms"], self.CHUNK_MS)
                base_l = EnvelopeFollower(config["baseline_attack_ms"], config["baseline_release_ms"], self.CHUNK_MS)
                fast_r = EnvelopeFollower(config["fast_attack_ms"], config["fast_release_ms"] * 0.7, self.CHUNK_MS)
                last_device_check = self.clock()

                while not self.stop_event.is_set():
                    if self.reload_event.is_set():
                        self.reload_event.clear()
                        break
                    now = self.clock()
                    if now - last_device_check >= self.DEVICE_CHECK_SECONDS:
                        last_device_check = now
                        if capture.default_output_changed():
                            break
                    data = capture.read()
                    if not self.enabled_provider():
                        self._set_motors(0, 0)
                        self._report_envelope(0.0)
                        continue
                    samples = pcm_float32(data, capture.channels)
                    low = lp.process(samples)
                    mid = bp.process(samples)
                    peak_low = max((abs(value) for value in low), default=0.0)
                    peak_mid = max((abs(value) for value in mid), default=0.0)
                    elf = fast_l.update(peak_low)
                    elb = base_l.update(peak_low)
                    transient = max(0.0, elf - elb)
                    erf = fast_r.update(peak_mid)
                    # Expose the real runtime audio envelope for the explicit
                    # DS5Forge-generated reactive trigger path only.
                    self._report_envelope(min(1.0, max(elf, erf)))
                    # Mapping-only parameters remain live without rebuilding the
                    # WASAPI stream/filter state, matching the upstream behavior.
                    mapping_config = self.config_provider()
                    left = map_rumble_level(elf, transient, mapping_config, texture=False)
                    right = map_rumble_level(erf, transient * 0.5, mapping_config, texture=True)
                    self._set_motors(left, right)
            finally:
                with self._capture_lock:
                    if self._active_capture is capture:
                        self._active_capture = None
        self._set_motors(0, 0)
        self._report_envelope(0.0)

    def _report_envelope(self, level: float) -> None:
        if self.on_envelope is not None:
            self.on_envelope(max(0.0, min(1.0, float(level))))

    def _set_motors(self, left: int, right: int) -> None:
        left = max(0, min(255, int(left)))
        right = max(0, min(255, int(right)))
        if abs(left - self.last_left) < 3 and abs(right - self.last_right) < 3:
            if not (left == 0 and right == 0 and (self.last_left or self.last_right)):
                return
        try:
            applied = self.motor_output(left, right)
            if applied is False:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_OUTPUT_FAILED,
                    "Rumble output was not accepted by the controller.",
                )
        except DS5ForgeError as exc:
            LOGGER.warning(
                "motor output was not applied",
                extra={"event": "audio.motor_output", "error_code": exc.code.value},
            )
            self._report_error(exc)
            return
        except Exception as exc:
            LOGGER.exception("motor output callback failed", extra={"event": "audio.motor_output"})
            wrapped = DS5ForgeError(ErrorCode.CONTROLLER_OUTPUT_FAILED, "Rumble output failed.", detail=str(exc))
            self._report_error(wrapped)
            return
        self.last_left, self.last_right = left, right
        if self.on_motors:
            self.on_motors(left, right)

    def _report_error(self, error: DS5ForgeError) -> None:
        if self.on_error:
            self.on_error(error)
