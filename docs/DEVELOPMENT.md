# P0 development and verification

Python 3.12.x is the required P0 development/build runtime. From the repository root:

```text
python -m venv .venv
python -m pip install -e ".[dev]"
ruff format source tests
ruff check source tests
mypy source/dualsense_companion
pytest
```

Headless core/API and the retained GUI are separate entry modes:

```text
python source/run.py --headless
python source/run.py
```

The GUI/API share one `CoreFacade` in the desktop process. Use injected fake
controller, capture and pointer adapters for tests; do not boot Bluetooth,
wireless transports or virtual-controller software.

The PyInstaller baseline remains available on Windows. `source/build.bat` validates that the active interpreter is Python 3.12.x before installing/building:

```text
cd source
build.bat
```

## Gate recording

- Format/lint/static checks: run in CI and record the exact command/result.
- Unit/integration tests: run without a controller; hardware adapters are
  tested by import/package checks and manual Windows USB smoke evidence.
- API smoke: use the FastAPI test client or loopback server and record health,
  state, config validation and command responses.
- WebSocket smoke: record initial snapshot, a state event and reconnect.
- USB checklist: complete `docs/D0_SMOKE_CHECKLIST.md` on Windows with a real
  cable/controller. Linux/CI results must remain `HARDWARE VALIDATION PENDING`.
