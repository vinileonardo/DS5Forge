import {
  AlertTriangle,
  FolderOpen,
  Gamepad2,
  LogOut,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button, Card, Field, Notice, PageHeader, Select, StatusPill, Toggle } from "../../components/ui";
import { api } from "../../lib/api/client";
import type {
  Chord,
  CompatibilityState,
  ConflictDiagnostic,
  ExclusiveCapability,
  ExclusiveStatus,
  GameCandidate,
  InputIsolationCapability,
  InputIsolationStatus,
  GameDefinition,
  Mapping,
  RuleEvaluation,
} from "../../lib/api/contracts";
import { formatRuntimeError, useRuntime } from "../../lib/runtime/RuntimeProvider";
import { useI18n, type Locale, type TranslationKey } from "../../lib/i18n";
import { pickExecutable } from "../../lib/tauri/gamePicker";

const EMPTY_GAME: GameDefinition = {
  id: "",
  name: "",
  executables: [],
  executable_path: null,
  profile: "Default",
  compatibility_mode: "native",
  adaptive_trigger_mode: "native",
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
  const { t } = useI18n();
  const mode = state?.mode ?? "native";
  const label =
    mode === "virtual"
      ? t("games.virtualXInput")
      : mode === "remap"
        ? t("shell.modeRemap")
        : t("shell.modeNative");
  return <StatusPill tone={state?.available === false ? "danger" : "success"} label={label} />;
}

function executableName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function generatedGameId(path: string): string {
  const stem = executableName(path).replace(/\.exe$/i, "");
  const slug = stem
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || `game-${Date.now()}`;
}

export function GamesPage() {
  const { runtime, profiles, coreStatus, stale, loading: runtimeLoading } = useRuntime();
  const { t, locale } = useI18n();
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
  const [candidates, setCandidates] = useState<GameCandidate[]>([]);
  const [exclusiveStatus, setExclusiveStatus] = useState<ExclusiveStatus | null>(null);
  const [exclusiveCapability, setExclusiveCapability] = useState<Awaited<
    ReturnType<typeof api.exclusiveCapabilities>
  > | null>(null);
  const [inputIsolationCapability, setInputIsolationCapability] = useState<InputIsolationCapability | null>(
    null,
  );
  const [inputIsolationStatus, setInputIsolationStatus] = useState<InputIsolationStatus | null>(null);

  const trustedRuntime = stale ? null : runtime;
  const automation = trustedRuntime?.automation;
  const foreground = trustedRuntime?.foreground;
  const activeGameId = automation?.active_game_id ?? null;
  const currentCompatibility = trustedRuntime?.compatibility;
  const displayedConflicts = useMemo(() => {
    const byProcess = new Map(conflicts.map((item) => [item.process.toLowerCase(), item]));
    for (const item of trustedRuntime?.conflicts ?? []) byProcess.set(item.process.toLowerCase(), item);
    return [...byProcess.values()];
  }, [conflicts, trustedRuntime?.conflicts]);
  const hasKnownConflict = displayedConflicts.some((item) => item.running);
  const statusLabel =
    coreStatus === "reconnecting"
      ? t("games.statusReconnecting")
      : stale || coreStatus !== "online"
        ? t("games.statusStale")
        : t("games.statusRealtime");

  const loadRegistry = useCallback(async () => {
    setLoading(true);
    setError(null);
    const results = await Promise.allSettled([
      api.games(),
      api.mappings(),
      api.chords(),
      api.conflictDiagnostics(),
      typeof api.gameCandidates === "function"
        ? api.gameCandidates()
        : Promise.resolve([] as GameCandidate[]),
    ]);
    const rejected = results.find((item): item is PromiseRejectedResult => item.status === "rejected");
    if (rejected) setError(rejected.reason);
    if (results[0]?.status === "fulfilled") setGames(results[0].value.games);
    if (results[1]?.status === "fulfilled") setMappings(results[1].value.mappings);
    if (results[2]?.status === "fulfilled") setChords(results[2].value.chords);
    if (results[3]?.status === "fulfilled") setConflicts(results[3].value.conflicts);
    if (results[4]?.status === "fulfilled") setCandidates(results[4].value);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  useEffect(() => {
    if (coreStatus !== "online") return;
    const capabilityRequest =
      typeof api.exclusiveCapabilities === "function" ? api.exclusiveCapabilities() : null;
    const statusRequest = typeof api.exclusiveStatus === "function" ? api.exclusiveStatus() : null;
    const isolationCapabilityRequest =
      typeof api.inputIsolationCapabilities === "function" ? api.inputIsolationCapabilities() : null;
    const isolationStatusRequest =
      typeof api.inputIsolationStatus === "function" ? api.inputIsolationStatus() : null;
    void Promise.allSettled([
      capabilityRequest,
      statusRequest,
      isolationCapabilityRequest,
      isolationStatusRequest,
    ]).then(([capability, status, isolationCapability, isolationStatus]) => {
      if (capability.status === "fulfilled" && capability.value) setExclusiveCapability(capability.value);
      if (status.status === "fulfilled" && status.value) setExclusiveStatus(status.value);
      if (isolationCapability.status === "fulfilled" && isolationCapability.value) {
        setInputIsolationCapability(isolationCapability.value);
      }
      if (isolationStatus.status === "fulfilled" && isolationStatus.value) {
        setInputIsolationStatus(isolationStatus.value);
      }
    });
  }, [coreStatus]);

  const activeGame = useMemo(
    () => games.find((game) => game.id === activeGameId) ?? automation?.active_game,
    [activeGameId, automation?.active_game, games],
  );

  async function selectExecutable() {
    try {
      const picked = await pickExecutable();
      if (!picked) return;
      setGameDraft((current) => ({
        ...current,
        id: current.id || generatedGameId(picked.name),
        name: current.name || picked.name.replace(/\.exe$/i, ""),
        executables: [picked.name],
        // The browser fallback cannot provide a verified path, so an identity
        // is stored instead of pretending a basename is an absolute path.
        executable_path: picked.path,
      }));
    } catch (reason) {
      setError(reason);
    }
  }

  function applyCandidate(candidate: GameCandidate) {
    const path = candidate.executable_path;
    const name = candidate.executable_name;
    setGameDraft((current) => ({
      ...current,
      id: current.id || generatedGameId(path || name),
      name: current.name || candidate.title || name.replace(/\.exe$/i, ""),
      executables: [name],
      executable_path: path,
    }));
  }

  async function toggleExclusive(enabled: boolean) {
    setPending("exclusive");
    setError(null);
    try {
      const next = enabled ? await api.enableExclusive() : await api.disableExclusive();
      setExclusiveStatus(next);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

  async function toggleInputIsolation(enabled: boolean) {
    setPending("input-isolation");
    setError(null);
    try {
      const next = enabled ? await api.enableInputIsolation() : await api.disableInputIsolation();
      setInputIsolationStatus(next);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(null);
    }
  }

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
    if (!window.confirm(`${t("games.removeRuleConfirm")}: ${id}?`)) return;
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
      setMatchReason(
        `${result.matched ? t("games.matched") : t("games.notMatched")}: ${localizedGameReason(result.reason, locale)}`,
      );
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
          eyebrow={t("games.eyebrow")}
          title={t("games.title")}
          description={t("games.loadingDescription")}
        />
        <Card>
          <div className="loading-state">
            <span className="spinner" aria-hidden="true" />
            {t("games.loadingDescription")}
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={t("games.eyebrow")}
        title={t("games.title")}
        description={t("games.description")}
        action={
          <Button variant="quiet" onClick={() => void loadRegistry()} disabled={loading}>
            <RefreshCw size={15} />
            {t("games.refreshRegistry")}
          </Button>
        }
      />

      {error && (
        <Notice tone="danger" title={t("games.dataUnavailable")}>
          {formatRuntimeError(error)}
        </Notice>
      )}
      {coreStatus !== "online" && (
        <Notice
          tone="warning"
          title={coreStatus === "reconnecting" ? t("games.reconnectingCore") : t("games.coreOffline")}
        >
          {t("games.coreStaleBody")}
        </Notice>
      )}

      <div className="overview-grid">
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.runningCandidates")}</h2>
              <p>{t("games.candidatesHelp")}</p>
            </div>
            <FolderOpen size={18} color="var(--accent)" />
          </div>
          {candidates.length ? (
            <div className="subsystem-list">
              {candidates.map((candidate) => (
                <div
                  className="subsystem"
                  key={`${candidate.executable_path ?? candidate.executable_name}-${candidate.pid ?? "recent"}`}
                >
                  <span>
                    <strong>{candidate.title || candidate.executable_name}</strong>
                    <small>
                      {candidate.executable_path || candidate.executable_name} ·{" "}
                      {candidate.source === "running"
                        ? t("games.candidateRunning")
                        : t("games.candidateRecent")}
                    </small>
                  </span>
                  <Button variant="quiet" onClick={() => applyCandidate(candidate)}>
                    {t("games.useCandidate")}
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">{t("games.noCandidates")}</p>
          )}
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>{t("exclusive.title")}</h2>
              <p>{t("games.exclusiveDescription")}</p>
            </div>
            <ShieldCheck size={18} color="var(--warning)" />
          </div>
          <Toggle
            label={t("games.exclusiveToggle")}
            description={
              exclusiveStatus?.enabled ? t("games.exclusiveActive") : t("games.exclusiveUnavailable")
            }
            checked={exclusiveStatus?.enabled ?? false}
            disabled={pending !== null || stale || !exclusiveOperational(exclusiveCapability)}
            onChange={(value) => void toggleExclusive(value)}
          />
          <dl className="data-list">
            <div className="data-item">
              <dt>{t("games.provider")}</dt>
              <dd>{exclusiveCapability?.provenance.provider ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>{t("games.outputReports")}</dt>
              <dd>
                {(exclusiveCapability?.virtual_output_reports ?? false) ? t("games.yes") : t("games.no")}
              </dd>
            </div>
            <div className="data-item">
              <dt>{t("games.suppressionVerified")}</dt>
              <dd>
                {(exclusiveCapability?.physical_suppression_verified ?? false)
                  ? t("games.yes")
                  : t("games.no")}
              </dd>
            </div>
            <div className="data-item">
              <dt>{t("games.doubleInputRisk")}</dt>
              <dd>{(exclusiveStatus?.double_input_risk ?? true) ? t("games.yes") : t("games.no")}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.foregroundTitle")}</h2>
              <p>{t("games.foregroundHelp")}</p>
            </div>
            <Terminal size={18} color="var(--accent)" />
          </div>
          <dl className="data-list">
            <div className="data-item">
              <dt>{t("games.executable")}</dt>
              <dd>{foreground?.executable_name ?? t("games.desktopUnavailable")}</dd>
            </div>
            <div className="data-item">
              <dt>{t("games.executablePath")}</dt>
              <dd>{foreground?.executable_path ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>PID</dt>
              <dd>{foreground?.pid ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>{t("games.windowTitle")}</dt>
              <dd>{foreground?.title ?? "—"}</dd>
            </div>
            <div className="data-item">
              <dt>{t("games.observation")}</dt>
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
              <h2>{t("games.activeGameTitle")}</h2>
              <p>{t("games.activeGameHelp")}</p>
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
                    {activeGame.executables.join(", ")} · {profileOriginLabel(automation?.profile_origin, t)}{" "}
                    · {t("games.profile")}
                  </p>
                </div>
              </div>
              <dl className="data-list">
                <div className="data-item">
                  <dt>{t("games.profile")}</dt>
                  <dd>{automation?.active_profile ?? activeGame.profile}</dd>
                </div>
                <div className="data-item">
                  <dt>{t("games.origin")}</dt>
                  <dd>{profileOriginLabel(automation?.profile_origin, t)}</dd>
                </div>
                <div className="data-item">
                  <dt>{t("games.rule")}</dt>
                  <dd>
                    {typeof automation?.last_match?.reason === "string"
                      ? localizedGameReason(automation.last_match.reason, locale)
                      : "—"}
                  </dd>
                </div>
                <div className="data-item">
                  <dt>{t("games.manualOverride")}</dt>
                  <dd>{automation?.manual_override ? t("games.overrideActive") : t("games.overrideNone")}</dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="empty-state" style={{ minHeight: 150 }}>
              <Gamepad2 size={26} />
              <h2>{t("games.noActiveGame")}</h2>
              <p>{t("games.noActiveGameHelp")}</p>
            </div>
          )}
          <Toggle
            label={t("games.automation")}
            description={automation?.enabled ? t("games.automationOn") : t("games.automationOff")}
            checked={automation?.enabled ?? false}
            disabled={pending !== null || stale}
            onChange={(value) => void toggleAutomation(value)}
          />
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.compatibilityTitle")}</h2>
              <p>{t("games.compatibilityHelp")}</p>
            </div>
            <ShieldAlert size={18} color="var(--warning)" />
          </div>
          <div className="stack">
            <CompatibilityLabel state={currentCompatibility} />
            <Field label={t("games.inputMode")} help={t("games.inputModeHelp")}>
              <Select
                aria-label={t("games.inputMode")}
                value={currentCompatibility?.mode ?? "native"}
                disabled={pending !== null || stale}
                onChange={(event) =>
                  void changeCompatibility(event.target.value as CompatibilityState["mode"])
                }
              >
                <option value="native">{t("games.nativeDualSense")}</option>
                <option value="remap">{t("games.remapKeyboardMouse")}</option>
                <option value="virtual" disabled={!virtualOperational(currentCompatibility)}>
                  {t("games.virtualXInput")}
                </option>
              </Select>
            </Field>
            {virtualOperational(currentCompatibility) ? (
              <Notice tone="info" title={t("games.virtualProviderAvailable")}>
                {t("games.virtualProviderAvailableBody")}
              </Notice>
            ) : (
              <Notice tone="warning" title={t("games.virtualUnavailable")}>
                {t("games.virtualUnavailableBody")}
              </Notice>
            )}
            {currentCompatibility?.double_input_risk && (
              <Notice tone="warning" title={t("games.possibleDoubleInput")}>
                {t("games.possibleDoubleInputBody")}
              </Notice>
            )}
            <div className="input-isolation-panel">
              <div>
                <strong>{t("games.inputIsolationTitle")}</strong>
                <p className="muted">{t("games.inputIsolationHelp")}</p>
              </div>
              <Toggle
                label={t("games.inputIsolationToggle")}
                description={
                  inputIsolationStatus?.active
                    ? t("games.inputIsolationActive")
                    : currentCompatibility?.mode !== "remap"
                      ? t("games.inputIsolationRemapOnly")
                      : inputIsolationOperational(inputIsolationCapability)
                        ? t("games.inputIsolationReady")
                        : t("games.inputIsolationUnavailable")
                }
                checked={inputIsolationStatus?.active ?? false}
                disabled={
                  pending !== null ||
                  stale ||
                  currentCompatibility?.mode !== "remap" ||
                  !inputIsolationOperational(inputIsolationCapability)
                }
                onChange={(value) => void toggleInputIsolation(value)}
              />
              <dl className="data-list compact-data-list">
                <div className="data-item">
                  <dt>{t("games.hidhideCloak")}</dt>
                  <dd>{inputIsolationStatus?.cloak_enabled ? t("games.yes") : t("games.no")}</dd>
                </div>
                <div className="data-item">
                  <dt>{t("games.ds5forgeAllowed")}</dt>
                  <dd>{inputIsolationStatus?.application_registered ? t("games.yes") : t("games.no")}</dd>
                </div>
                <div className="data-item">
                  <dt>{t("games.deviceHidden")}</dt>
                  <dd>{inputIsolationStatus?.device_hidden ? t("games.yes") : t("games.no")}</dd>
                </div>
              </dl>
            </div>
            <dl className="data-list">
              <div className="data-item">
                <dt>{t("games.physicalVisible")}</dt>
                <dd>
                  {(currentCompatibility?.physical_input_visible ?? true) ? t("games.yes") : t("games.no")}
                </dd>
              </div>
              <div className="data-item">
                <dt>{t("games.virtualActive")}</dt>
                <dd>
                  {(currentCompatibility?.virtual_input_active ?? false) ? t("games.yes") : t("games.no")}
                </dd>
              </div>
              <div className="data-item">
                <dt>{t("games.doubleInputRisk")}</dt>
                <dd>{(currentCompatibility?.double_input_risk ?? false) ? t("games.yes") : t("games.no")}</dd>
              </div>
            </dl>
          </div>
        </Card>

        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.exitPolicyTitle")}</h2>
              <p>{t("games.exitPolicyHelp")}</p>
            </div>
            <LogOut size={18} color="var(--accent)" />
          </div>
          <Field label={t("games.onExit")}>
            <Select
              aria-label={t("games.onExit")}
              value={automation?.exit_policy ?? "restore_previous"}
              disabled={pending !== null || stale}
              onChange={(event) =>
                void changeExitPolicy(
                  event.target.value as "restore_previous" | "apply_default" | "keep_current",
                )
              }
            >
              <option value="restore_previous">{t("games.restorePrevious")}</option>
              <option value="apply_default">{t("games.applyDefault")}</option>
              <option value="keep_current">{t("games.keepCurrent")}</option>
            </Select>
          </Field>
          <p className="muted">{t("games.manualOverrideHelp")}</p>
        </Card>
      </div>

      <div className="stack" style={{ marginTop: 18 }}>
        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.registryTitle")}</h2>
              <p>{t("games.registryHelp")}</p>
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
                      label={game.enabled ? t("games.enabled") : t("games.disabled")}
                    />
                    <Button
                      variant="quiet"
                      onClick={() => {
                        setGameDraft(game);
                        setEditingGameId(game.id);
                      }}
                    >
                      {t("games.edit")}
                    </Button>
                    <Button
                      variant="quiet"
                      onClick={() => void testMatch(game.id)}
                      disabled={pending !== null || stale}
                    >
                      {t("games.testMatch")}
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => void removeGame(game.id)}
                      disabled={pending !== null || stale}
                    >
                      {t("games.remove")}
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">{t("games.noGames")}</p>
            )}
          </div>
          {matchReason && (
            <Notice tone="info" title={t("games.matchExplanation")}>
              {matchReason}
            </Notice>
          )}
          {matchEvaluations.length > 0 && (
            <div className="subsystem-list" aria-label={t("games.ruleEvaluations")}>
              {matchEvaluations.map((evaluation) => (
                <div className="subsystem" key={evaluation.game_id}>
                  <span>
                    {evaluation.game_name}
                    <small className="muted">{localizedGameReason(evaluation.reason, locale)}</small>
                  </span>
                  <StatusPill
                    tone={evaluation.matched ? "success" : "neutral"}
                    label={evaluation.matched ? ruleActionLabel(evaluation.action, t) : t("games.notMatched")}
                  />
                </div>
              ))}
            </div>
          )}
          <div className="form-grid" style={{ marginTop: 18 }}>
            <Field label={t("games.ruleId")}>
              <input
                className="input"
                value={gameDraft.id}
                disabled={editingGameId !== null}
                onChange={(event) => setGameDraft({ ...gameDraft, id: event.target.value })}
                placeholder="elden-ring"
              />
            </Field>
            <Field label={t("games.displayName")}>
              <input
                className="input"
                value={gameDraft.name}
                onChange={(event) => setGameDraft({ ...gameDraft, name: event.target.value })}
                placeholder="Elden Ring"
              />
            </Field>
            <Field label={t("games.executables")} help={t("games.executablesHelp")}>
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
            <Field label={t("games.optionalPath")} help={t("games.optionalPathHelp")}>
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
            <Field label={t("games.profile")} help={t("games.profileHelp")}>
              <Select
                aria-label={t("games.profile")}
                value={gameDraft.profile}
                onChange={(event) => setGameDraft({ ...gameDraft, profile: event.target.value })}
              >
                {[
                  "Default",
                  ...(profiles ?? []).map((profile) => profile.name).filter((name) => name !== "Default"),
                ].map((profile) => (
                  <option key={profile} value={profile}>
                    {profile}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("games.automationMode")}>
              <Select
                value={gameDraft.compatibility_mode}
                onChange={(event) =>
                  setGameDraft({
                    ...gameDraft,
                    compatibility_mode: event.target.value as GameDefinition["compatibility_mode"],
                  })
                }
              >
                <option value="native">{t("shell.modeNative")}</option>
                <option value="remap">{t("shell.modeRemap")}</option>
                <option value="virtual" disabled={!virtualOperational(currentCompatibility)}>
                  {t("games.virtualXInput")}
                </option>
              </Select>
            </Field>
            <Field label={t("games.adaptiveTriggerMode")} help={t("games.adaptiveTriggerModeHelp")}>
              <Select
                aria-label={t("games.adaptiveTriggerMode")}
                value={gameDraft.adaptive_trigger_mode}
                onChange={(event) =>
                  setGameDraft({
                    ...gameDraft,
                    adaptive_trigger_mode: event.target.value as GameDefinition["adaptive_trigger_mode"],
                  })
                }
              >
                <option value="native">{t("games.adaptiveNative")}</option>
                <option value="reactive">{t("games.adaptiveReactive")}</option>
                <option value="off">{t("games.adaptiveOff")}</option>
              </Select>
            </Field>
            <Toggle
              label={t("games.ruleEnabled")}
              description={t("games.ruleEnabledHelp")}
              checked={gameDraft.enabled}
              disabled={pending !== null || stale}
              onChange={(value) => setGameDraft({ ...gameDraft, enabled: value })}
            />
          </div>
          <div className="form-actions">
            <Button
              variant="quiet"
              onClick={() => void selectExecutable()}
              disabled={pending !== null || stale}
            >
              <FolderOpen size={15} /> {t("games.pickExecutable")}
            </Button>
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
              {pending === "game" ? t("games.saving") : t("games.saveGameRule")}
            </Button>
            <Button
              variant="quiet"
              onClick={() => {
                setGameDraft(EMPTY_GAME);
                setEditingGameId(null);
              }}
            >
              {t("games.clear")}
            </Button>
          </div>
        </Card>

        <details className="settings-advanced games-advanced" open>
          <summary>{t("games.advancedMappings")}</summary>
          <div className="stack">
            <Card>
              <div className="card-header">
                <div>
                  <h2>{t("games.mappings")}</h2>
                  <p>{t("games.mappingsHelp")}</p>
                </div>
              </div>
              {mappings.map((mapping) => (
                <div className="subsystem" key={mapping.id}>
                  <span>
                    {mapping.input} → {mapping.output_kind}:{mapping.output_code}
                    {mapping.game_id ? ` · ${mapping.game_id}` : ` · ${t("games.allGames")}`}
                  </span>
                  <div className="form-actions">
                    <Button
                      variant="quiet"
                      onClick={() => {
                        setMappingDraft(mapping);
                        setEditingMappingId(mapping.id);
                      }}
                    >
                      {t("games.edit")}
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => void removeMapping(mapping.id)}
                      disabled={pending !== null || stale}
                    >
                      {t("games.remove")}
                    </Button>
                  </div>
                </div>
              ))}
              <div className="form-grid" style={{ marginTop: 14 }}>
                <Field label={t("games.mappingId")}>
                  <input
                    className="input"
                    value={mappingDraft.id}
                    disabled={editingMappingId !== null}
                    onChange={(event) => setMappingDraft({ ...mappingDraft, id: event.target.value })}
                    placeholder="cross-space"
                  />
                </Field>
                <Field label={t("games.controllerInput")}>
                  <input
                    className="input"
                    value={mappingDraft.input}
                    onChange={(event) => setMappingDraft({ ...mappingDraft, input: event.target.value })}
                  />
                </Field>
                <Field label={t("games.outputKind")}>
                  <Select
                    value={mappingDraft.output_kind}
                    onChange={(event) =>
                      setMappingDraft({
                        ...mappingDraft,
                        output_kind: event.target.value as Mapping["output_kind"],
                      })
                    }
                  >
                    <option value="keyboard">{t("games.keyboard")}</option>
                    <option value="mouse">{t("games.mouse")}</option>
                  </Select>
                </Field>
                <Field
                  label={t("games.outputCode")}
                  help={
                    mappingDraft.output_kind === "keyboard"
                      ? t("games.keyboardCodeHelp")
                      : t("games.mouseCodeHelp")
                  }
                >
                  <input
                    className="input"
                    value={mappingDraft.output_code}
                    onChange={(event) =>
                      setMappingDraft({ ...mappingDraft, output_code: event.target.value })
                    }
                  />
                </Field>
                <Field label={t("games.gameScope")} help={t("games.mappingScopeHelp")}>
                  <input
                    className="input"
                    aria-label={t("games.gameScope")}
                    value={mappingDraft.game_id ?? ""}
                    onChange={(event) =>
                      setMappingDraft({ ...mappingDraft, game_id: event.target.value.trim() || null })
                    }
                    placeholder="elden-ring"
                  />
                </Field>
                <Field label={t("games.debounce")}>
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
                label={t("games.mappingEnabled")}
                description={t("games.mappingEnabledHelp")}
                checked={mappingDraft.enabled}
                disabled={pending !== null || stale}
                onChange={(value) => setMappingDraft({ ...mappingDraft, enabled: value })}
              />
              <div className="form-actions">
                <Button
                  onClick={() => void saveMapping()}
                  disabled={pending !== null || stale || !mappingDraft.id}
                >
                  {pending === "mapping" ? t("games.saving") : t("games.saveMapping")}
                </Button>
                <Button
                  variant="quiet"
                  onClick={() => {
                    setMappingDraft(EMPTY_MAPPING);
                    setEditingMappingId(null);
                  }}
                >
                  {t("games.clear")}
                </Button>
              </div>
            </Card>

            <Card>
              <div className="card-header">
                <div>
                  <h2>{t("games.chords")}</h2>
                  <p>{t("games.chordsHelp")}</p>
                </div>
              </div>
              {chords.map((chord) => (
                <div className="subsystem" key={chord.id}>
                  <span>
                    {chord.inputs.join(" + ")} → {chord.output_kind}:{chord.output_code}
                    {chord.game_id ? ` · ${chord.game_id}` : ` · ${t("games.allGames")}`}
                  </span>
                  <div className="form-actions">
                    <Button
                      variant="quiet"
                      onClick={() => {
                        setChordDraft(chord);
                        setEditingChordId(chord.id);
                      }}
                    >
                      {t("games.edit")}
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => void removeChord(chord.id)}
                      disabled={pending !== null || stale}
                    >
                      {t("games.remove")}
                    </Button>
                  </div>
                </div>
              ))}
              <div className="form-grid" style={{ marginTop: 14 }}>
                <Field label={t("games.chordId")}>
                  <input
                    className="input"
                    value={chordDraft.id}
                    disabled={editingChordId !== null}
                    onChange={(event) => setChordDraft({ ...chordDraft, id: event.target.value })}
                    placeholder="l1-r1-escape"
                  />
                </Field>
                <Field label={t("games.inputsComma")}>
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
                <Field label={t("games.outputKind")}>
                  <Select
                    value={chordDraft.output_kind}
                    onChange={(event) =>
                      setChordDraft({
                        ...chordDraft,
                        output_kind: event.target.value as Chord["output_kind"],
                      })
                    }
                  >
                    <option value="keyboard">{t("games.keyboard")}</option>
                    <option value="mouse">{t("games.mouse")}</option>
                  </Select>
                </Field>
                <Field
                  label={t("games.outputCode")}
                  help={
                    chordDraft.output_kind === "keyboard"
                      ? t("games.keyboardCodeHelp")
                      : t("games.mouseCodeHelp")
                  }
                >
                  <input
                    className="input"
                    value={chordDraft.output_code}
                    onChange={(event) => setChordDraft({ ...chordDraft, output_code: event.target.value })}
                  />
                </Field>
                <Field label={t("games.gameScope")} help={t("games.chordScopeHelp")}>
                  <input
                    className="input"
                    aria-label={t("games.gameScope")}
                    value={chordDraft.game_id ?? ""}
                    onChange={(event) =>
                      setChordDraft({ ...chordDraft, game_id: event.target.value.trim() || null })
                    }
                    placeholder="elden-ring"
                  />
                </Field>
                <Field label={t("games.chordWindow")}>
                  <input
                    className="input"
                    type="number"
                    min={25}
                    max={1000}
                    value={chordDraft.window_ms}
                    onChange={(event) =>
                      setChordDraft({ ...chordDraft, window_ms: Number(event.target.value) })
                    }
                  />
                </Field>
                <Field label={t("games.debounce")}>
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
                label={t("games.chordEnabled")}
                description={t("games.chordEnabledHelp")}
                checked={chordDraft.enabled}
                disabled={pending !== null || stale}
                onChange={(value) => setChordDraft({ ...chordDraft, enabled: value })}
              />
              <div className="form-actions">
                <Button
                  onClick={() => void saveChord()}
                  disabled={pending !== null || stale || !chordDraft.id || chordDraft.inputs.length < 2}
                >
                  {pending === "chord" ? t("games.saving") : t("games.saveChord")}
                </Button>
                <Button
                  variant="quiet"
                  onClick={() => {
                    setChordDraft(EMPTY_CHORD);
                    setEditingChordId(null);
                  }}
                >
                  {t("games.clear")}
                </Button>
              </div>
            </Card>
          </div>
        </details>

        <Card>
          <div className="card-header">
            <div>
              <h2>{t("games.conflictDiagnostics")}</h2>
              <p>{t("games.conflictDiagnosticsHelp")}</p>
            </div>
            <AlertTriangle size={18} color="var(--warning)" />
          </div>
          {hasKnownConflict && (
            <Notice tone="warning" title={t("games.possibleInputConflict")}>
              {t("games.possibleInputConflictBody")}
            </Notice>
          )}
          <div className="subsystem-list">
            {displayedConflicts.map((item) => (
              <div className="subsystem" key={item.process}>
                <span>
                  {item.process}
                  <small className="muted">{localizedConflictMessage(item, locale)}</small>
                </span>
                <StatusPill
                  tone={conflictTone(item)}
                  label={
                    item.running
                      ? item.severity === "warning"
                        ? t("games.conflictWarning")
                        : t("games.conflictInfo")
                      : t("games.notDetected")
                  }
                />
              </div>
            ))}
          </div>
        </Card>
      </div>
      <span className="sr-only">
        {runtimeLoading ? t("games.runtimeLoading") : pending ? `${pending} ${t("games.pending")}` : ""}
      </span>
    </>
  );
}

function virtualOperational(state: CompatibilityState | undefined): boolean {
  const capability = state?.virtual_capability;
  return Boolean(capability?.installed && capability.available && capability.physical_suppression_supported);
}

function exclusiveOperational(capability: ExclusiveCapability | null): boolean {
  if (!capability) return false;
  return Boolean(
    capability.provider_available &&
    capability.provider_installed &&
    capability.virtual_output_reports &&
    capability.physical_suppression_available &&
    capability.physical_suppression_verified &&
    capability.provenance.signature_verified &&
    capability.provenance.provenance_verified &&
    capability.provenance.integrity_verified &&
    capability.provenance.windows_validated,
  );
}

function inputIsolationOperational(capability: InputIsolationCapability | null): boolean {
  return Boolean(
    capability?.installed &&
    capability.available &&
    capability.application_path &&
    capability.device_detected &&
    capability.device_instance_path,
  );
}

function profileOriginLabel(
  origin: "manual" | "automatic" | undefined,
  t: (key: TranslationKey) => string,
): string {
  if (origin === "automatic") return t("games.originAutomatic");
  if (origin === "manual") return t("games.originManual");
  return "—";
}

function ruleActionLabel(action: string, t: (key: TranslationKey) => string): string {
  if (action === "activate") return t("games.actionActivate");
  if (action === "none") return t("games.actionNone");
  return action;
}

function localizedGameReason(reason: string, locale: Locale): string {
  if (locale !== "pt-BR") return reason;
  const exact: Record<string, string> = {
    "Executable name and configured path matched.": "O executável corresponde à regra configurada.",
    "Configured process is running and currently owns foreground priority.":
      "O processo configurado está em execução e tem prioridade por estar em primeiro plano.",
    "Configured process is still running in the background.":
      "O processo configurado continua em execução em segundo plano.",
    "Configured process is running.": "O processo configurado está em execução.",
    "Configured process is running, but another live game currently has priority.":
      "O processo configurado está em execução, mas outro jogo aberto tem prioridade no momento.",
    "No configured executable for this rule is currently running.":
      "Nenhum executável configurado para esta regra está em execução.",
    "Rule is disabled.": "A regra está desativada.",
    "No live foreground process is available.": "Nenhum processo em primeiro plano está disponível.",
    "Executable name matched, but its full path was unavailable.":
      "O nome do executável corresponde, mas o caminho completo não pôde ser verificado.",
    "No registered game rule matched the foreground executable.":
      "Nenhuma regra de jogo corresponde ao executável observado.",
    "No registered game rule matched a running process.":
      "Nenhuma regra de jogo corresponde a um processo em execução.",
  };
  if (exact[reason]) return exact[reason];
  if (reason.startsWith("Executable path does not match")) {
    return "O caminho do executável não corresponde ao caminho configurado para esta regra.";
  }
  if (reason.startsWith("Executable '") && reason.includes("does not match any configured executable")) {
    return "O executável observado não corresponde aos executáveis configurados para esta regra.";
  }
  return "O estado da regra foi atualizado pelo núcleo local.";
}

function localizedConflictMessage(item: ConflictDiagnostic, locale: Locale): string {
  if (locale !== "pt-BR") return item.message;
  if (!item.running) return `${item.process} não foi detectado.`;
  if (item.process.toLowerCase() === "steam.exe") {
    return "A Steam está em execução. O Steam Input pode afetar o controle dependendo da configuração do jogo.";
  }
  return `${item.process} está em execução e pode remapear ou virtualizar a entrada do controle.`;
}
