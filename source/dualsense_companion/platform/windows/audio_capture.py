"""Windows audio capture adapters.

The legacy adapter captures the default render endpoint. DS5Forge's product
composition uses the process-loopback adapter instead so reactive haptics only
see audio emitted by the active game's process tree.
"""

from __future__ import annotations

import array
import importlib.metadata
import importlib.util
import sys
import threading
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...diagnostics.logging import get_logger
from ...domain.errors import DS5ForgeError, ErrorCode, PlatformUnavailableError

LOGGER = get_logger(__name__)


class WasapiLoopbackFactory:
    """Legacy whole-device loopback used only by the standalone legacy path."""

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


@dataclass(frozen=True, slots=True)
class ProcessAudioTarget:
    """One process tree selected as the only reactive-audio source."""

    pid: int
    app_name: str
    executable_name: str | None = None

    def __post_init__(self) -> None:
        if int(self.pid) <= 0:
            raise ValueError("pid must be positive")
        object.__setattr__(self, "pid", int(self.pid))
        object.__setattr__(self, "app_name", str(self.app_name).strip() or f"PID {self.pid}")
        if self.executable_name is not None:
            executable = str(self.executable_name).strip()
            object.__setattr__(self, "executable_name", executable or None)

    @property
    def label(self) -> str:
        process = self.executable_name or self.app_name
        return f"{self.app_name} — {process} (PID {self.pid})"


class WasapiProcessLoopbackFactory:
    """Selects a live game PID and opens WASAPI process-loopback capture.

    The selected PID is mutable because game automation owns process lifecycle.
    Each open capture snapshots a generation. A PID/game transition increments
    that generation so HapticsService tears down the old stream deterministically.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._target: ProcessAudioTarget | None = None
        self._generation = 0

    def select_process(
        self,
        pid: int,
        *,
        app_name: str,
        executable_name: str | None = None,
    ) -> bool:
        target = ProcessAudioTarget(pid=pid, app_name=app_name, executable_name=executable_name)
        with self._lock:
            if target == self._target:
                return False
            self._target = target
            self._generation += 1
        LOGGER.info(
            "reactive audio target selected",
            extra={
                "event": "audio.process_target",
                "pid": target.pid,
                "game": target.app_name,
                "process": target.executable_name,
            },
        )
        return True

    def clear_process(self) -> bool:
        with self._lock:
            if self._target is None:
                return False
            previous = self._target
            self._target = None
            self._generation += 1
        LOGGER.info(
            "reactive audio target cleared",
            extra={"event": "audio.process_target_cleared", "pid": previous.pid, "game": previous.app_name},
        )
        return True

    def is_ready(self) -> bool:
        with self._lock:
            return self._target is not None

    def waiting_description(self) -> str:
        return "Waiting for active game process"

    def current_target(self) -> ProcessAudioTarget | None:
        with self._lock:
            return self._target

    def _snapshot(self) -> tuple[ProcessAudioTarget | None, int]:
        with self._lock:
            return self._target, self._generation

    def _current_generation(self) -> int:
        with self._lock:
            return self._generation

    def open(self) -> WasapiProcessLoopbackCapture:
        target, generation = self._snapshot()
        if target is None:
            raise PlatformUnavailableError(
                "No active game process is selected for reactive audio.",
                detail="DS5Forge intentionally does not fall back to whole-system loopback.",
            )
        return WasapiProcessLoopbackCapture(
            target=target,
            generation=generation,
            generation_provider=self._current_generation,
        )


def _load_process_loopback_class() -> Any:
    """Load only ProcTap's native WASAPI extension, not its DSP dependency tree."""

    module_name = "proctap._native"
    existing = sys.modules.get(module_name)
    if existing is not None and hasattr(existing, "ProcessLoopback"):
        return existing.ProcessLoopback

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend(sorted((Path(meipass) / "proctap").glob("_native*.pyd")))
    else:
        try:
            distribution = importlib.metadata.distribution("proc-tap")
        except importlib.metadata.PackageNotFoundError as exc:
            raise PlatformUnavailableError(
                "The ProcTap native process-loopback dependency is not installed.",
                detail=str(exc),
            ) from exc
        for item in distribution.files or ():
            normalized = str(item).replace("\\", "/")
            if normalized.startswith("proctap/_native.") and normalized.endswith(".pyd"):
                candidates.append(Path(str(distribution.locate_file(item))))

    native_path = next((path for path in candidates if path.is_file()), None)
    if native_path is None:
        raise PlatformUnavailableError(
            "The ProcTap native process-loopback module could not be located.",
            detail="Expected proctap/_native*.pyd.",
        )

    parent_created = False
    if "proctap" not in sys.modules:
        package = types.ModuleType("proctap")
        package.__path__ = [str(native_path.parent)]  # type: ignore[attr-defined]
        package.__package__ = "proctap"
        sys.modules["proctap"] = package
        parent_created = True

    spec = importlib.util.spec_from_file_location(module_name, native_path)
    if spec is None or spec.loader is None:
        if parent_created:
            sys.modules.pop("proctap", None)
        raise PlatformUnavailableError(
            "The ProcTap native process-loopback module could not be loaded.",
            detail=str(native_path),
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        if parent_created:
            sys.modules.pop("proctap", None)
        raise PlatformUnavailableError(
            "The ProcTap native process-loopback module could not be loaded.",
            detail=str(exc),
        ) from exc

    process_loopback = getattr(module, "ProcessLoopback", None)
    if process_loopback is None:
        raise PlatformUnavailableError(
            "The ProcTap native module does not expose ProcessLoopback.",
            detail=str(native_path),
        )
    return process_loopback


def _int16_to_float32(data: bytes) -> bytes:
    samples = array.array("h")
    samples.frombytes(data[: len(data) - (len(data) % 2)])
    if sys.byteorder != "little":
        samples.byteswap()
    floats = array.array("f", (sample / 32768.0 for sample in samples))
    if sys.byteorder != "little":
        floats.byteswap()
    return floats.tobytes()


class WasapiProcessLoopbackCapture:
    """Raw process-tree audio capture backed only by ProcTap's native WASAPI module."""

    CHUNK_MS = 10

    def __init__(
        self,
        *,
        target: ProcessAudioTarget,
        generation: int,
        generation_provider: Any,
    ) -> None:
        self.target = target
        self._generation = int(generation)
        self._generation_provider = generation_provider
        self._capture: Any = None
        self._bits_per_sample = 32
        self.sample_rate = 48_000
        self.channels = 2
        self.frames = int(self.sample_rate * self.CHUNK_MS / 1000)
        self.name = f"{target.label} [process loopback]"

    def __enter__(self) -> WasapiProcessLoopbackCapture:
        try:
            process_loopback = _load_process_loopback_class()
            capture = process_loopback(self.target.pid)
            format_info = capture.get_format()
            self.sample_rate = max(1, int(format_info.get("sample_rate", 48_000)))
            self.channels = max(1, int(format_info.get("channels", 2)))
            self._bits_per_sample = int(format_info.get("bits_per_sample", 32))
            if self._bits_per_sample not in {16, 32}:
                raise RuntimeError(f"unsupported process-loopback sample width: {self._bits_per_sample} bits")
            self.frames = max(64, int(self.sample_rate * self.CHUNK_MS / 1000))
            capture.start()
            self._capture = capture
            return self
        except DS5ForgeError:
            raise
        except Exception as exc:
            self.close()
            raise DS5ForgeError(
                ErrorCode.AUDIO_CAPTURE_FAILED,
                "Per-process WASAPI loopback could not be opened.",
                detail=str(exc),
                fields={
                    "pid": self.target.pid,
                    "game": self.target.app_name,
                    "process": self.target.executable_name,
                },
            ) from exc

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def read(self) -> bytes:
        capture = self._capture
        if capture is None:
            raise DS5ForgeError(ErrorCode.AUDIO_CAPTURE_FAILED, "Process audio capture stream is not open.")
        try:
            # The native API is non-blocking. Bound the poll so PID/game
            # transitions still interrupt promptly without spinning a CPU core.
            deadline = time.monotonic() + 0.10
            data: bytes | None = None
            while data is None and time.monotonic() < deadline:
                candidate = capture.read()
                data = bytes(candidate) if candidate else None
                if data is None:
                    time.sleep(0.002)
            if not data:
                return b""
            return _int16_to_float32(data) if self._bits_per_sample == 16 else data
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.AUDIO_CAPTURE_FAILED,
                "Per-process audio capture read failed.",
                detail=str(exc),
                fields={"pid": self.target.pid, "game": self.target.app_name},
            ) from exc

    def default_output_changed(self) -> bool:
        """For process loopback, a target-generation change replaces device change."""

        try:
            return int(self._generation_provider()) != self._generation
        except Exception as exc:
            LOGGER.warning(
                "could not check process audio target generation",
                extra={"event": "audio.process_target_check", "error": str(exc)},
            )
            return False

    def close(self) -> None:
        capture, self._capture = self._capture, None
        if capture is None:
            return
        try:
            capture.stop()
        except Exception:
            LOGGER.debug("process audio capture stop failed", exc_info=True)
