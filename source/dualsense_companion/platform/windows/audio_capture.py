"""Lazy PyAudioWPatch WASAPI loopback capture adapter."""

from __future__ import annotations

from typing import Any

from ...diagnostics.logging import get_logger
from ...domain.errors import DS5ForgeError, ErrorCode, PlatformUnavailableError

LOGGER = get_logger(__name__)


class WasapiLoopbackFactory:
    def open(self) -> WasapiLoopbackCapture:
        return WasapiLoopbackCapture()


class WasapiLoopbackCapture:
    CHUNK_MS = 10

    def __init__(self) -> None:
        self._pyaudio: Any = None
        self._stream: Any = None
        self._default_index: int | None = None
        self._wasapi_type: int | None = None
        self.sample_rate = 0
        self.channels = 0
        self.frames = 0
        self.name = ""

    def __enter__(self) -> WasapiLoopbackCapture:
        try:
            import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PlatformUnavailableError(
                "The PyAudioWPatch WASAPI dependency is not installed.",
                detail=str(exc),
            ) from exc
        try:
            self._pyaudio = pyaudio.PyAudio()
            self._wasapi_type = int(pyaudio.paWASAPI)
            wasapi = self._pyaudio.get_host_api_info_by_type(self._wasapi_type)
            self._default_index = int(wasapi["defaultOutputDevice"])
            default_out = self._pyaudio.get_device_info_by_index(self._default_index)
            loopback = default_out
            if not default_out.get("isLoopbackDevice"):
                for candidate in self._pyaudio.get_loopback_device_info_generator():
                    if default_out["name"] in candidate["name"]:
                        loopback = candidate
                        break
            self.sample_rate = int(loopback["defaultSampleRate"])
            self.channels = max(1, int(loopback["maxInputChannels"]))
            self.frames = max(64, int(self.sample_rate * self.CHUNK_MS / 1000))
            self.name = str(loopback["name"])
            self._stream = self._pyaudio.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=loopback["index"],
                frames_per_buffer=self.frames,
            )
            return self
        except Exception as exc:
            self.close()
            raise DS5ForgeError(
                ErrorCode.AUDIO_CAPTURE_FAILED,
                "WASAPI loopback could not be opened.",
                detail=str(exc),
            ) from exc

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def read(self) -> bytes:
        if self._stream is None:
            raise DS5ForgeError(ErrorCode.AUDIO_CAPTURE_FAILED, "Audio capture stream is not open.")
        try:
            return self._stream.read(self.frames, exception_on_overflow=False)
        except Exception as exc:
            raise DS5ForgeError(ErrorCode.AUDIO_CAPTURE_FAILED, "Audio capture read failed.", detail=str(exc)) from exc

    def default_output_changed(self) -> bool:
        if self._pyaudio is None or self._default_index is None or self._wasapi_type is None:
            return False
        try:
            wasapi = self._pyaudio.get_host_api_info_by_type(self._wasapi_type)
            return int(wasapi["defaultOutputDevice"]) != self._default_index
        except Exception as exc:
            LOGGER.warning(
                "could not check default audio device", extra={"event": "audio.device_check", "error": str(exc)}
            )
            return False

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                LOGGER.debug("audio stream close failed", exc_info=True)
            finally:
                self._stream = None
        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:
                LOGGER.debug("PyAudio terminate failed", exc_info=True)
            finally:
                self._pyaudio = None
                self._wasapi_type = None
