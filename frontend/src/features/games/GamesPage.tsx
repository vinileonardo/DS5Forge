import { AlertTriangle, Gamepad2, LogOut, RefreshCw, ShieldAlert, Terminal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, Card, Field, Notice, PageHeader, Select, StatusPill, Toggle } from "../../components/ui";
import { api } from "../../lib/api/client";
import type {
  Chord,
  CompatibilityState,
  ConflictDiagnostic,
  GameDefinition,
  Mapping,
  RuleEvaluation,
} from "../../lib/api/contracts";
import { formatRuntimeError, useRuntime } from "../../lib/runtime/RuntimeProvider";

const EMPTY_GAME: GameDefinition = {
  id: "",
  name: "",
  executables: [],
  executable_path: null,
  profile: "Default",
  compatibility_mode: "native",
  enabled: true,
};

const EMPTY_MAPPING: Mapping = {
  id: "",
  input: "cross",
  output_kind: "keyboard",
  output_code: "SPACE",
  game_id: null,
  enabled: true,
  debounce_ms: 25,
};

const EMPTY_CHORD: Chord = {
  id: "",
  inputs: ["l1", "r1"],
  output_kind: "keyboard",
  output_code: "ESC",
  game_id: null,
  enabled: true,
  window_ms: 250,
  debounce_ms: 25,
};

function conflictTone(item: ConflictDiagnostic): "success" | "warning" | "danger" | "neutral" {
  if (!item.running) return "neutral";
  return item.severity === "danger" ? "danger" : "warning";
}

function CompatibilityLabel({ state }: { state: CompatibilityState | undefined }) {
  const mode = state?.mode ?? "native";
  const label = mode === "virtual" ? "Virtual / XInput" : mode === "remap" ? "Remap" : "Native";
  return <StatusPill tone={state?.available === false ? "danger" : "success"} label={label} />;
}

export function GamesPage() {
  const { runtime, coreStatus, stale, loading: runtimeLoading } = useRuntime();
  const [games, setGames] = useState<GameDefinition[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [chords, setChords] = useState<Chord[]>([]);
  const [conflicts, setConflicts] = useState<ConflictDiagnostic[]>([]);
  const [gameDraft, setGameDraft] = useState<GameDefinition>(EMPTY_GAME);
  const [mappingDraft, setMappingDraft] = useState<Mapping>(EMPTY_MAPPING);
  const [chordDraft, setChordDraft] = useState<Chord>(EMPTY_CHORD);
  const [editingGameId, setEditingGameId] = useState<string | null>(null);
  const [editingMappingId, setEditingMappingId] = useState<string | null>(null);
  const [editingChordId, setEditingChordId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [matchReason, setMatchReason] = useState<string | null>(null);
  const [matchEvaluations, setMatchEvaluations] = useState<RuleEvaluation[]>([]);

  const automation = runtime?.automation;
  const foreground = runtime?.foreground;
  const activeGameId = automation?.active_game_id ?? null;
  const currentCompatibility = runtime?.compatibility;
  const displayedConflicts = useMemo(() => {
    const byProcess = new Map(conflicts.map((item) => [item.process.toLowerCase(), item]));
    for (const item of runtime?.conflicts ?? []) byProcess.set(item.process.toLowerCase(), item);
    return [...byProcess.values()];
  }, [conflicts, runtime?.conflicts]);
  const hasKnownConflict = displayedConflicts.some((item) => item.running);
  const statusLabel =
    coreStatus === "reconnecting" ? "reconnecting" : stale || coreStatus !== "online" ? "stale" : "realtime";

  const loadRegistry = useCallback(async () => {
    setLoading(true);
    setError(null);
    const results = await Promise.allSettled([
      api.games(),
      api.mappings(),
      api.chords(),
      api.conflictDiagnostics(),
    ]);
    const rejected = results.find((item): item is PromiseRejectedResult => item.status === "rejected");
    if (rejected) setError(rejected.reason);
    if (results[0]?.status === "fulfilled") setGames(results[0].value.games);
    if (results[1]?.status === "fulfilled") setMappings(results[1].value.mappings);
    if (results[2]?.status === "fulfilled") setChords(results[2].value.chords);
    if (results[3]?.status === "fulfilled") setConflicts(results[3].value.conflicts);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  const activeGame = useMemo(
    () => games.find((game) => game.id === activeGameId) ?? automation?.active_game,
    [activeGameId, automation?.active_game, games],
  );

  async function saveGame() {
    setPending("game");
    setError(null);
    try {
      const executables = gameDraft.executables.map((item) => item.trim()).filter(Boolean);
      const candidate = {
        ...gameDraft,
        executables,
        executable_path: executables.length === 1 ? gameDraft.executable_path : null,
      };
      const saved = editingGameId
        ? await api.updateGame(editingGameId, { ...candidate, id: editingGameId })
        : await api.addGame(candidate);
      setGames((current) => {
        if (editingGameId) return current.map((game) => (game.id === editingGameId ? saved : game));
        return [...current, saved];
      });
      setGameDraft(EMPTY_GAME);
      setEditingGameId(null);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function removeGame(id: string) {
    if (!window.confirm(`Remove the ${id} game rule?`)) return;
    setPending(`delete-${id}`);
    try {
      await api.deleteGame(id);
      setGames((current) => current.filter((game) => game.id !== id));
      if (editingGameId === id) {
        setGameDraft(EMPTY_GAME);
        setEditingGameId(null);
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function testMatch(id: string) {
    setPending(`match-${id}`);
    try {
      const result = await api.testGameMatch(id);
      setMatchReason(`${result.matched ? "Matched" : "Not matched"}: ${result.reason}`);
      setMatchEvaluations(result.evaluations);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function toggleAutomation(enabled: boolean) {
    setPending("automation");
    try {
      await api.updateAutomation({ enabled });
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function changeCompatibility(mode: CompatibilityState["mode"]) {
    setPending("compatibility");
    try {
      await api.updateCompatibility(mode);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function changeExitPolicy(exit_policy: "restore_previous" | "apply_default" | "keep_current") {
    setPending("exit-policy");
    try {
      await api.updateAutomation({ exit_policy });
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function saveMapping() {
    setPending("mapping");
    setError(null);
    try {
      const candidate = { ...mappingDraft, id: editingMappingId ?? mappingDraft.id };
      const next = editingMappingId
        ? mappings.map((item) => (item.id === editingMappingId ? candidate : item))
        : [...mappings, candidate];
      setMappings((await api.updateMappings(next)).mappings);
      setMappingDraft(EMPTY_MAPPING);
      setEditingMappingId(null);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function removeMapping(id: string) {
    setPending(`delete-mapping-${id}`);
    setError(null);
    try {
      setMappings((await api.updateMappings(mappings.filter((item) => item.id !== id))).mappings);
      if (editingMappingId === id) {
        setMappingDraft(EMPTY_MAPPING);
        setEditingMappingId(null);
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function saveChord() {
    setPending("chord");
    setError(null);
    try {
      const candidate = { ...chordDraft, id: editingChordId ?? chordDraft.id };
      const next = editingChordId
        ? chords.map((item) => (item.id === editingChordId ? candidate : item))
        : [...chords, candidate];
      setChords((await api.updateChords(next)).chords);
      setChordDraft(EMPTY_CHORD);
      setEditingChordId(null);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function removeChord(id: string) {
    setPending(`delete-chord-${id}`);
    setError(null);
    try {
      setChords((await api.updateChords(chords.filter((item) => item.id !== id))).chords);
      if (editingChordId === id) {
        setChordDraft(EMPTY_CHORD);
        setEditingChordId(null);
      }
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  if (loading && games.length === 0) {
    return (
      <>
        <PageHeader
          eyebrow="Compatibility control"
          title="Games"
          description="Loading the local game registry…"
        />
        <Card>
          <div className="loading-state">
            <span className="spinner" aria-hidden="true" />
            Loading games, mappings and diagnostics
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Compatibility control"
        title="Games"
        description="Apply profiles by foreground executable while keeping Native DualSense input as the safe default."
        action={
          <Button variant="quiet" onClick={() => void loadRegistry()} disabled={loading}>
            <RefreshCw size={15} />
            Refresh registry
          </Button>
        }
      />

      {error && (
        <Notice tone="danger" title="Games data unavailable">
          {formatRuntimeError(error)}
        </Notice>
      )}
      {coreStatus !== "online" && (
        <Notice
          tone="warning"
          title={coreStatus === "reconnecting" ? "Reconnecting local core" : "Local core offline"}
        >
          The registry may still be visible, but foreground, active-game and automation state are stale until
          the WebSocket reconnects.
        </Notice>
      )}

      <div className="overview-grid">
        <Card>
          <div className="card-header">
            <div>
              <h2>Foreground</h2>
              <p>Identity uses the executable, never the mutable window title.</p>
            </div>
            <Terminal size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>Executable</dt>
              <dd>{foreground?.executable_name ?? "Desktop / unavailable"}</dd>
            </div>
            <div className="data-item">
              <dt>Executable path</dt>
              <dd>{foreground?.executable_path ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>PID</dt>
              <dd>{foreground?.pid ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>Window title</dt>
              <dd>{foreground?.title ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>Observation</dt>
              <dd>
                {foreground?.observed_at ? new Date(foreground.observed_at * 1000).toLocaleTimeString() : "—"}
              </dd>
            </div>
          </dl>
          {foreground?.diagnostic && <p className="muted">{foreground.diagnostic}</p>}
          <div className="form-actions">
            <StatusPill tone={stale ? "warning" : "success"} label={statusLabel} detail="WebSocket" />
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Active game</h2>
              <p>Updates from realtime state without a page reload.</p>
            </div>
            <Gamepad2 size={18} color="var(--violet)" />
          </div>
          {activeGame ? (
            <>
              <div className="hero-state">
                <div className="hero-state-mark">
                  <Gamepad2 size={21} />
                </div>
                <div>
                  <h2>{activeGame.name}</h2>
                  <p>
                    {activeGame.executables.join(", ")} · {automation?.profile_origin ?? "unknown"} profile
                  </p>
                </div>
              </div>
              <dl className="data-list">
                <div className="data-item">
                  <dt>Profile</dt>
                  <dd>{automation?.active_profile ?? activeGame.profile}</dd>
                </div>
                <div className="data-item">
                  <dt>Origin</dt>
                  <dd>{automation?.profile_origin ?? "—"}</dd>
                </div>
                <div className="data-item">
                  <dt>Rule</dt>
                  <dd>
                    {typeof automation?.last_match?.reason === "string" ? automation.last_match.reason : "—"}
                  </dd>
                </div>
                <div className="data-item">
                  <dt>Manual override</dt>
                  <dd>{automation?.manual_override ? "active" : "none"}</dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="empty-state" style={{ minHeight: 150 }}>
              <Gamepad2 size={26} />
              <h2>No active game</h2>
              <p>Foreground is not currently matched by an enabled rule.</p>
            </div>
          )}
          <Toggle
            label="Game automation"
            description={
              automation?.enabled ? "Rules are evaluated on real foreground transitions" : "Automation is off"
            }
            checked={automation?.enabled ?? false}
            disabled={pending !== null || stale}
            onChange={(value) => void toggleAutomation(value)}
          />
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Compatibility mode</h2>
              <p>Mode changes release all synthetic outputs before applying.</p>
            </div>
            <ShieldAlert size={18} color="var(--warning)" />
          </div>
          <div className="stack">
            <CompatibilityLabel state={currentCompatibility} />
            <Field
              label="Input mode"
              help="Native never creates synthetic output. Remap does not require XInput."
            >
              <Select
                aria-label="Input mode"
                value={currentCompatibility?.mode ?? "native"}
                disabled={pending !== null || stale}
                onChange={(event) =>
                  void changeCompatibility(event.target.value as CompatibilityState["mode"])
                }
              >
                <option value="native">Native DualSense</option>
                <option value="remap">Remap keyboard/mouse</option>
                <option value="virtual" disabled={!virtualOperational(currentCompatibility)}>
                  Virtual / XInput
                </option>
              </Select>
            </Field>
            {virtualOperational(currentCompatibility) ? (
              <Notice tone="info" title="Virtual provider available">
                Physical suppression is reported by the injected provider and remains explicit.
              </Notice>
            ) : (
              <Notice tone="warning" title="Virtual / XInput unavailable">
                No approved provider with reliable physical suppression is installed in P3. The requested mode
                will be rejected and Native/Remap state will remain unchanged.
              </Notice>
            )}
            {currentCompatibility?.double_input_risk && (
              <Notice tone="warning" title="Possible double input in Remap">
                {currentCompatibility.reason ??
                  "Remap adds synthetic keyboard/mouse output while the physical controller remains visible."}
              </Notice>
            )}
            <dl className="data-list">
              <div className="data-item">
                <dt>Physical input visible</dt>
                <dd>{String(currentCompatibility?.physical_input_visible ?? true)}</dd>
              </div>
              <div className="data-item">
                <dt>Virtual input active</dt>
                <dd>{String(currentCompatibility?.virtual_input_active ?? false)}</dd>
              </div>
              <div className="data-item">
                <dt>Double-input risk</dt>
                <dd>{String(currentCompatibility?.double_input_risk ?? false)}</dd>
              </div>
            </dl>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Exit policy</h2>
              <p>What happens when the foreground game closes or changes to desktop.</p>
            </div>
            <LogOut size={18} color="var(--accent)" />
          </div>
          <Field label="On game exit">
            <Select
              aria-label="On game exit"
              value={automation?.exit_policy ?? "restore_previous"}
              disabled={pending !== null || stale}
              onChange={(event) =>
                void changeExitPolicy(
                  event.target.value as "restore_previous" | "apply_default" | "keep_current",
                )
              }
            >
              <option value="restore_previous">Restore previous profile</option>
              <option value="apply_default">Apply Default profile</option>
              <option value="keep_current">Keep current state</option>
            </Select>
          </Field>
          <p className="muted">
            Manual profile or mode changes mark the active context as a manual override until a real
            foreground transition.
          </p>
        </Card>
      </div>

      <div className="stack" style={{ marginTop: 18 }}>
        <Card>
          <div className="card-header">
            <div>
              <h2>Game registry</h2>
              <p>
                Match one or more executable names, with an optional exact path for single-executable rules.
              </p>
            </div>
          </div>
          <div className="game-registry-list">
            {games.length ? (
              games.map((game) => (
                <div className="subsystem" key={game.id}>
                  <div>
                    <strong>{game.name}</strong>
                    <p className="muted">
                      {game.executables.join(", ")}
                      {game.executable_path ? ` · ${game.executable_path}` : ""} · {game.profile}
                    </p>
                  </div>
                  <div className="form-actions">
                    <StatusPill
                      tone={game.enabled ? "success" : "neutral"}
                      label={game.enabled ? "Enabled" : "Disabled"}
                    />
                    <Button
                      variant="quiet"
                      onClick={() => {
                        setGameDraft(game);
                        setEditingGameId(game.id);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="quiet"
                      onClick={() => void testMatch(game.id)}
                      disabled={pending !== null || stale}
                    >
                      Test match
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => void removeGame(game.id)}
                      disabled={pending !== null || stale}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">No games registered. Add an executable rule below.</p>
            )}
          </div>
          {matchReason && (
            <Notice tone="info" title="Match explanation">
              {matchReason}
            </Notice>
          )}
          {matchEvaluations.length > 0 && (
            <div className="subsystem-list" aria-label="Rule evaluations">
              {matchEvaluations.map((evaluation) => (
                <div className="subsystem" key={evaluation.game_id}>
                  <span>
                    {evaluation.game_name}
                    <small className="muted">{evaluation.reason}</small>
                  </span>
                  <StatusPill
                    tone={evaluation.matched ? "success" : "neutral"}
                    label={evaluation.matched ? evaluation.action : "not matched"}
                  />
                </div>
              ))}
            </div>
          )}
          <div className="form-grid" style={{ marginTop: 18 }}>
            <Field label="Rule ID">
              <input
                className="input"
                value={gameDraft.id}
                disabled={editingGameId !== null}
                onChange={(event) => setGameDraft({ ...gameDraft, id: event.target.value })}
                placeholder="elden-ring"
              />
            </Field>
            <Field label="Display name">
              <input
                className="input"
                value={gameDraft.name}
                onChange={(event) => setGameDraft({ ...gameDraft, name: event.target.value })}
                placeholder="Elden Ring"
              />
            </Field>
            <Field
              label="Executables"
              help="Comma-separated process names, for example game.exe, launcher.exe."
            >
              <input
                className="input"
                value={gameDraft.executables.join(", ")}
                onChange={(event) => {
                  const executables = event.target.value.split(",").map((item) => item.trim());
                  setGameDraft({
                    ...gameDraft,
                    executables,
                    executable_path:
                      executables.filter(Boolean).length === 1 ? gameDraft.executable_path : null,
                  });
                }}
                placeholder="eldenring.exe, launcher.exe"
              />
            </Field>
            <Field
              label="Optional full path"
              help="Only available when the rule has exactly one executable name."
            >
              <input
                className="input"
                value={gameDraft.executable_path ?? ""}
                disabled={gameDraft.executables.filter(Boolean).length !== 1}
                onChange={(event) =>
                  setGameDraft({ ...gameDraft, executable_path: event.target.value || null })
                }
                placeholder="C:\\Games\\eldenring.exe"
              />
            </Field>
            <Field label="Profile">
              <input
                className="input"
                value={gameDraft.profile}
                onChange={(event) => setGameDraft({ ...gameDraft, profile: event.target.value })}
              />
            </Field>
            <Field label="Automation mode">
              <Select
                value={gameDraft.compatibility_mode}
                onChange={(event) =>
                  setGameDraft({
                    ...gameDraft,
                    compatibility_mode: event.target.value as GameDefinition["compatibility_mode"],
                  })
                }
              >
                <option value="native">Native</option>
                <option value="remap">Remap</option>
                <option value="virtual" disabled={!virtualOperational(currentCompatibility)}>
                  Virtual / XInput
                </option>
              </Select>
            </Field>
            <Toggle
              label="Rule enabled"
              description="Evaluate these executable identities during foreground transitions."
              checked={gameDraft.enabled}
              disabled={pending !== null || stale}
              onChange={(value) => setGameDraft({ ...gameDraft, enabled: value })}
            />
          </div>
          <div className="form-actions">
            <Button
              onClick={() => void saveGame()}
              disabled={
                pending !== null ||
                stale ||
                !gameDraft.id ||
                !gameDraft.name ||
                gameDraft.executables.every((item) => !item.trim())
              }
            >
              {pending === "game" ? "Saving…" : "Save game rule"}
            </Button>
            <Button
              variant="quiet"
              onClick={() => {
                setGameDraft(EMPTY_GAME);
                setEditingGameId(null);
              }}
            >
              Clear
            </Button>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Mappings</h2>
              <p>Controller button to validated keyboard or mouse output.</p>
            </div>
          </div>
          {mappings.map((mapping) => (
            <div className="subsystem" key={mapping.id}>
              <span>
                {mapping.input} → {mapping.output_kind}:{mapping.output_code}
                {mapping.game_id ? ` · ${mapping.game_id}` : " · all games"}
              </span>
              <div className="form-actions">
                <Button
                  variant="quiet"
                  onClick={() => {
                    setMappingDraft(mapping);
                    setEditingMappingId(mapping.id);
                  }}
                >
                  Edit
                </Button>
                <Button
                  variant="danger"
                  onClick={() => void removeMapping(mapping.id)}
                  disabled={pending !== null || stale}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
          <div className="form-grid" style={{ marginTop: 14 }}>
            <Field label="Mapping ID">
              <input
                className="input"
                value={mappingDraft.id}
                disabled={editingMappingId !== null}
                onChange={(event) => setMappingDraft({ ...mappingDraft, id: event.target.value })}
                placeholder="cross-space"
              />
            </Field>
            <Field label="Controller input">
              <input
                className="input"
                value={mappingDraft.input}
                onChange={(event) => setMappingDraft({ ...mappingDraft, input: event.target.value })}
              />
            </Field>
            <Field label="Output kind">
              <Select
                value={mappingDraft.output_kind}
                onChange={(event) =>
                  setMappingDraft({
                    ...mappingDraft,
                    output_kind: event.target.value as Mapping["output_kind"],
                  })
                }
              >
                <option value="keyboard">Keyboard</option>
                <option value="mouse">Mouse</option>
              </Select>
            </Field>
            <Field
              label="Output code"
              help={
                mappingDraft.output_kind === "keyboard"
                  ? "Use one key or a + combination, for example SPACE or CTRL+SHIFT+S."
                  : "Use left, right, middle, mouse4 or mouse5."
              }
            >
              <input
                className="input"
                value={mappingDraft.output_code}
                onChange={(event) => setMappingDraft({ ...mappingDraft, output_code: event.target.value })}
              />
            </Field>
            <Field
              label="Game scope (optional)"
              help="Leave blank to apply this mapping in every remap context."
            >
              <input
                className="input"
                aria-label="Mapping game scope"
                value={mappingDraft.game_id ?? ""}
                onChange={(event) =>
                  setMappingDraft({ ...mappingDraft, game_id: event.target.value.trim() || null })
                }
                placeholder="elden-ring"
              />
            </Field>
            <Field label="Debounce (ms)">
              <input
                className="input"
                type="number"
                min={1}
                max={500}
                value={mappingDraft.debounce_ms}
                onChange={(event) =>
                  setMappingDraft({ ...mappingDraft, debounce_ms: Number(event.target.value) })
                }
              />
            </Field>
          </div>
          <Toggle
            label="Mapping enabled"
            description="Allow this mapping to produce output in its configured scope."
            checked={mappingDraft.enabled}
            disabled={pending !== null || stale}
            onChange={(value) => setMappingDraft({ ...mappingDraft, enabled: value })}
          />
          <div className="form-actions">
            <Button
              onClick={() => void saveMapping()}
              disabled={pending !== null || stale || !mappingDraft.id}
            >
              {pending === "mapping" ? "Saving…" : "Save mapping"}
            </Button>
            <Button
              variant="quiet"
              onClick={() => {
                setMappingDraft(EMPTY_MAPPING);
                setEditingMappingId(null);
              }}
            >
              Clear
            </Button>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Chords</h2>
              <p>Two or more inputs; chords take precedence during the bounded activation window.</p>
            </div>
          </div>
          {chords.map((chord) => (
            <div className="subsystem" key={chord.id}>
              <span>
                {chord.inputs.join(" + ")} → {chord.output_kind}:{chord.output_code}
                {chord.game_id ? ` · ${chord.game_id}` : " · all games"}
              </span>
              <div className="form-actions">
                <Button
                  variant="quiet"
                  onClick={() => {
                    setChordDraft(chord);
                    setEditingChordId(chord.id);
                  }}
                >
                  Edit
                </Button>
                <Button
                  variant="danger"
                  onClick={() => void removeChord(chord.id)}
                  disabled={pending !== null || stale}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
          <div className="form-grid" style={{ marginTop: 14 }}>
            <Field label="Chord ID">
              <input
                className="input"
                value={chordDraft.id}
                disabled={editingChordId !== null}
                onChange={(event) => setChordDraft({ ...chordDraft, id: event.target.value })}
                placeholder="l1-r1-escape"
              />
            </Field>
            <Field label="Inputs (comma-separated)">
              <input
                className="input"
                value={chordDraft.inputs.join(",")}
                onChange={(event) =>
                  setChordDraft({
                    ...chordDraft,
                    inputs: event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean),
                  })
                }
              />
            </Field>
            <Field label="Output kind">
              <Select
                value={chordDraft.output_kind}
                onChange={(event) =>
                  setChordDraft({ ...chordDraft, output_kind: event.target.value as Chord["output_kind"] })
                }
              >
                <option value="keyboard">Keyboard</option>
                <option value="mouse">Mouse</option>
              </Select>
            </Field>
            <Field
              label="Output code"
              help={
                chordDraft.output_kind === "keyboard"
                  ? "Use one key or a + combination, for example F5 or CTRL+SHIFT+S."
                  : "Use left, right, middle, mouse4 or mouse5."
              }
            >
              <input
                className="input"
                value={chordDraft.output_code}
                onChange={(event) => setChordDraft({ ...chordDraft, output_code: event.target.value })}
              />
            </Field>
            <Field
              label="Game scope (optional)"
              help="Leave blank to apply this chord in every remap context."
            >
              <input
                className="input"
                aria-label="Chord game scope"
                value={chordDraft.game_id ?? ""}
                onChange={(event) =>
                  setChordDraft({ ...chordDraft, game_id: event.target.value.trim() || null })
                }
                placeholder="elden-ring"
              />
            </Field>
            <Field label="Chord window (ms)">
              <input
                className="input"
                type="number"
                min={25}
                max={1000}
                value={chordDraft.window_ms}
                onChange={(event) => setChordDraft({ ...chordDraft, window_ms: Number(event.target.value) })}
              />
            </Field>
            <Field label="Debounce (ms)">
              <input
                className="input"
                type="number"
                min={1}
                max={500}
                value={chordDraft.debounce_ms}
                onChange={(event) =>
                  setChordDraft({ ...chordDraft, debounce_ms: Number(event.target.value) })
                }
              />
            </Field>
          </div>
          <Toggle
            label="Chord enabled"
            description="Allow this chord to win over simple mappings during its bounded window."
            checked={chordDraft.enabled}
            disabled={pending !== null || stale}
            onChange={(value) => setChordDraft({ ...chordDraft, enabled: value })}
          />
          <div className="form-actions">
            <Button
              onClick={() => void saveChord()}
              disabled={pending !== null || stale || !chordDraft.id || chordDraft.inputs.length < 2}
            >
              {pending === "chord" ? "Saving…" : "Save chord"}
            </Button>
            <Button
              variant="quiet"
              onClick={() => {
                setChordDraft(EMPTY_CHORD);
                setEditingChordId(null);
              }}
            >
              Clear
            </Button>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>Conflict diagnostics</h2>
              <p>Process-name evidence only; DS5Forge never kills or reconfigures other software.</p>
            </div>
            <AlertTriangle size={18} color="var(--warning)" />
          </div>
          {hasKnownConflict && (
            <Notice tone="warning" title="Possible input conflict">
              A remapper or Steam process is running. Its active input configuration was not inferred.
            </Notice>
          )}
          <div className="subsystem-list">
            {displayedConflicts.map((item) => (
              <div className="subsystem" key={item.process}>
                <span>
                  {item.process}
                  <small className="muted">{item.message}</small>
                </span>
                <StatusPill tone={conflictTone(item)} label={item.running ? item.severity : "not detected"} />
              </div>
            ))}
          </div>
        </Card>
      </div>
      <span className="sr-only">
        {runtimeLoading ? "Runtime loading" : pending ? `${pending} pending` : ""}
      </span>
    </>
  );
}

function virtualOperational(state: CompatibilityState | undefined): boolean {
  const capability = state?.virtual_capability;
  return Boolean(capability?.installed && capability.available && capability.physical_suppression_supported);
}
