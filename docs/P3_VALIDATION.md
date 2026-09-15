# DS5Forge P3 validation record

Independent review status: `GO` for P3 automated/source evidence. Physical
Windows + DualSense USB evidence remains `HARDWARE VALIDATION PENDING` and is
still required before a physical release GO.

## Baseline and repository safety

- Base: `a9df75c0018230b219e323c6ca159f286a6093d3`.
- Branch: `feat/p3-compat-games-automation`.
- Independent review completed on the same branch; no commit, push, merge or
  deploy is part of this validation record.
- Existing untracked `docs/P2_REVIEW_SCOPE.json` and
  `docs/P2_REVIEW_SCOPE_V2.json` are user-owned and preserved.

## Python/core gates

Run from the repository root with Python 3.12:

```text
./.venv/bin/ruff format --check source tests
./.venv/bin/ruff check source tests
./.venv/bin/mypy source/dualsense_companion
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q source tests
python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/ds5forge-p3-wheel
git diff --check
```

Recorded on 2026-09-14 with Python 3.12.3:

- `ruff format --check`: PASS — 68 files already formatted.
- `ruff check`: PASS.
- `mypy`: PASS — no issues in 48 source files.
- `pytest -q`: PASS — 107 passed in 2.06s.
- `compileall`: PASS.
- Wheel: PASS with `python3 -m pip wheel`; independent review produced
  `ds5forge-0.1.0-py3-none-any.whl` (114451 bytes, SHA-256
  `cdb9827840c077047b9682480df32337c3f6be8b0770ba0a33113b40e0188696`).
- `git diff --check`: PASS.

Required P3 coverage includes strict registry/recovery/atomic writes,
executable matching and explanation, fake foreground failures and bounded
shutdown, all exit policies, A → B and game → desktop, manual override,
mapping/chord debounce and precedence, scoped rules, synthetic release with
partial failures, disconnect/shutdown/rollback, compatibility gating/fake
provider, conflict diagnostics, API routes and versioned event behavior.
Independent-review regressions additionally cover 64-bit Win32 handle
signatures, longest-window chord fallback, subset-chord rejection, failed A → B
recovery, transition/remap serialization, Remap double-input diagnostics,
strict `synthetic.release` WebSocket validation and shared touchpad/remap mouse
ownership.

## Frontend gates

Run from `frontend/`:

```text
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
npm audit --omit=dev
```

Recorded on 2026-09-14:

- `npm ci`: PASS — 326 packages added, 327 audited, 0 vulnerabilities.
- Prettier: PASS.
- ESLint: PASS with zero warnings/errors.
- TypeScript: PASS.
- Vitest: PASS — 12 files and 41 tests in 1.76s.
- Vite build: PASS — 1,645 modules transformed.
- Playwright: PASS — 11 tests in 3.5s.
- `npm audit --omit=dev`: PASS — 0 vulnerabilities.

Games coverage includes the foreground/active-game projection, automation and
exit policy controls, match explanation, strict mode selection, Virtual
unavailability, registry/mapping/chord editors, mapping/chord removal and stable
edit identity, conflict warning tone, stale/offline states, strict P3 socket
payloads and reconnect without reload.

## Source/boundary audits

```text
./.venv/bin/pytest -q tests/test_boundaries.py tests/test_p3_compat_games.py
matches=$(rg -n -i '\b(bluetooth|wireless|pairing|dongle|vigembus|hidhide)\b' source frontend/src frontend/src-tauri --glob '*.py' --glob '*.ts' --glob '*.tsx' --glob '*.json' --glob '*.toml' --glob '*.rs' || true); if [ -n "$matches" ]; then printf '%s\n' "$matches"; exit 1; fi; echo 'implementation wired-only audit: PASS'
rg -n 'pydualsense|WASAPI|ctypes\.windll|SendInput\(' source/dualsense_companion
```

Recorded on 2026-09-14:

- Boundary and P3 safety tests: PASS — 27 passed in 0.56s.
- Wired-only implementation audit: PASS — no forbidden transport/provider
  terms in implementation paths.
- Platform ownership review: PASS — controller/WASAPI/Win32 output references
  remain in `platform/windows`; core matches are comments/contracts only.
- Tauri static audit: PASS — `core:default` only, bundle inactive, no
  sidecar/process/fs permissions.

The first audit must keep hardware APIs in `platform/windows`, keep the core
free of platform imports and find no silent operational `except: pass`. The
second is a review aid: P3 documentation may mention deferred capabilities,
but no implementation or permission path may add them. Tauri remains the
existing minimal `core:default` shell with no sidecar/process permissions.

## Windows and physical USB limitations

The following are not proven by Linux or mocked Playwright runs:

- Win32 foreground PID/path/title inspection;
- Windows `SendInput` keyboard/mouse behavior;
- packaged Windows/PyInstaller behavior;
- authenticated backend operation on Windows;
- a real DualSense connected by USB, including game transitions, haptics,
  touchpad and teardown;
- any production virtual-controller provider or physical suppression.

Complete [`D0_SMOKE_CHECKLIST.md`](D0_SMOKE_CHECKLIST.md) on Windows with a
real wired controller before any physical release GO. The independent code
review is `GO`; the separate physical-evidence status remains exactly
`HARDWARE VALIDATION PENDING`.
