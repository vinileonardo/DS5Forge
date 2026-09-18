import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  type Config,
  type ConfigPatch,
  type ControllerProfile,
  type GestureConfig,
  type HealthResponse,
  type HapticsTestRun,
  type LightbarState,
  type PlayerLedState,
  type ProfileLoadResponse,
  type ProfileSaveResponse,
  type ProfileSummary,
  type RuntimeState,
  type StickCalibration,
  type StickCalibrationEstimate,
  type StickTelemetry,
  type TriggerEffect,
  type TriggerPreview,
  type TriggerState,
} from "../api/contracts";
import { api, websocketUrl } from "../api/client";
import { ApiError, ApiProtocolError, errorMessage, isNetworkError } from "../api/errors";
import {
  applyRuntimeEvent,
  sessionEventFor,
  type RuntimeProjection,
  type SessionEvent,
} from "../realtime/reducer";
import { RealtimeSocket, type SocketStatus } from "../realtime/socket";

export type CoreStatus = SocketStatus;

export type RuntimeView = RuntimeProjection & {
  health: HealthResponse | null;
  profiles: ProfileSummary[];
  coreStatus: CoreStatus;
  loading: boolean;
  stale: boolean;
  lastReconnectAt: number | null;
  reconnectAttempt: number;
  events: SessionEvent[];
  clientErrors: string[];
};

type RuntimeContextValue = RuntimeView & {
  refresh: () => Promise<void>;
  updateConfig: (patch: ConfigPatch) => Promise<Config>;
  setRumble: (enabled: boolean) => Promise<RuntimeState>;
  setTouchpad: (enabled: boolean) => Promise<RuntimeState>;
  testRumble: (payload?: { left?: number; right?: number; duration_ms?: number }) => Promise<boolean>;
  loadProfile: (name: string) => Promise<Config>;
  loadControllerProfile: (name: string) => Promise<ProfileLoadResponse>;
  saveProfile: (name: string, rumble: Partial<NonNullable<Config>["rumble"]>) => Promise<void>;
  saveControllerProfile: (
    name: string,
    profile: ControllerProfile,
    confirmOverwrite?: boolean,
  ) => Promise<ProfileSaveResponse>;
  exportProfile: (name: string) => Promise<ControllerProfile>;
  importProfile: (content: string, name?: string, confirmOverwrite?: boolean) => Promise<ControllerProfile>;
  deleteProfile: (name: string) => Promise<void>;
  applyLightbar: (state: LightbarState) => Promise<LightbarState>;
  resetLightbar: () => Promise<LightbarState>;
  applyPlayerLeds: (state: PlayerLedState) => Promise<PlayerLedState>;
  resetPlayerLeds: () => Promise<PlayerLedState>;
  applyTriggers: (state: { left: TriggerEffect; right: TriggerEffect }) => Promise<TriggerState>;
  previewTriggers: (
    state: { left: TriggerEffect; right: TriggerEffect },
    durationMs: number,
  ) => Promise<TriggerPreview>;
  cancelTriggerPreview: () => Promise<TriggerPreview | null>;
  resetTriggers: () => Promise<TriggerState>;
  startHapticsTest: (payload: {
    left: number;
    right: number;
    duration_ms: number;
  }) => Promise<HapticsTestRun>;
  cancelHapticsTest: () => Promise<HapticsTestRun | null>;
  updateStickCalibration: (calibration: StickCalibration) => Promise<StickCalibration>;
  estimateStickCalibration: (samples: StickTelemetry[]) => Promise<StickCalibrationEstimate>;
  updateGestures: (patch: Partial<GestureConfig>) => Promise<GestureConfig>;
  canControl: boolean;
};

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

const initialView: RuntimeView = {
  runtime: null,
  config: null,
  health: null,
  profiles: [],
  coreStatus: "offline",
  loading: true,
  stale: true,
  lastReconnectAt: null,
  reconnectAttempt: 0,
  events: [],
  clientErrors: [],
};

const EMPTY_TRIGGERS: TriggerState = {
  left: { mode: "off", start_position: 0, end_position: 255, force: 0, frequency: 0, amplitude: 0 },
  right: { mode: "off", start_position: 0, end_position: 255, force: 0, frequency: 0, amplitude: 0 },
  preview: null,
};

// A reachable WebSocket transport is not enough to trust controller state: the
// latest validated snapshot must also report a connected controller. Commands
// reuse this so a disconnected snapshot is never silently marked fresh.
function stateIsStale(status: CoreStatus, runtime: RuntimeState | null): boolean {
  return status !== "online" || runtime?.connection !== "connected";
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<RuntimeView>(initialView);
  const nextEventId = useRef(0);
  const mounted = useRef(true);

  const addClientError = useCallback((message: string) => {
    setView((current) => ({
      ...current,
      clientErrors: [message, ...current.clientErrors].slice(0, 8),
    }));
  }, []);

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([api.health(), api.state(), api.config(), api.profiles()]);
    if (!mounted.current) return;
    const [healthResult, stateResult, configResult, profilesResult] = results;
    const networkFailure = results.some(
      (result) => result.status === "rejected" && isNetworkError(result.reason),
    );
    const protocolFailure = results.find(
      (result): result is PromiseRejectedResult =>
        result.status === "rejected" && result.reason instanceof ApiProtocolError,
    );
    if (protocolFailure) addClientError(errorMessage(protocolFailure.reason));
    setView((current) => {
      const runtime = stateResult.status === "fulfilled" ? stateResult.value : current.runtime;
      return {
        ...current,
        health: healthResult.status === "fulfilled" ? healthResult.value : current.health,
        runtime,
        config: configResult.status === "fulfilled" ? configResult.value : current.config,
        profiles: profilesResult.status === "fulfilled" ? profilesResult.value.profiles : current.profiles,
        coreStatus: networkFailure || stateResult.status === "rejected" ? "offline" : current.coreStatus,
        loading: false,
        stale:
          networkFailure || stateResult.status === "rejected" || stateIsStale(current.coreStatus, runtime),
      };
    });
  }, [addClientError]);

  useEffect(() => {
    mounted.current = true;
    const socket = new RealtimeSocket({
      url: websocketUrl(),
      onStatus: (status) => {
        if (!mounted.current) return;
        setView((current) => ({
          ...current,
          coreStatus: status,
          stale: stateIsStale(status, current.runtime),
          reconnectAttempt: socket.reconnectAttempt,
          loading: false,
        }));
      },
      onEvent: (event) => {
        if (!mounted.current) return;
        setView((current) => {
          const projection = applyRuntimeEvent(current, event);
          const entry = sessionEventFor(event, ++nextEventId.current);
          const eventIsStale =
            event.type === "controller.lifecycle"
              ? event.payload.state !== "connected"
              : event.type === "state.snapshot" || event.type === "state.updated"
                ? event.payload.state.connection !== "connected"
                : event.type === "controller.input"
                  ? current.runtime?.connection !== "connected"
                  : current.stale;
          return {
            ...current,
            ...projection,
            events: [entry, ...current.events].slice(0, 50),
            stale: eventIsStale,
            loading: false,
          };
        });
      },
      onProtocolError: (error) => {
        if (!mounted.current) return;
        addClientError(error.message);
      },
      onReconnect: (recovered) => {
        if (!mounted.current) return;
        if (recovered) setView((current) => ({ ...current, lastReconnectAt: Date.now() }));
        void refresh();
      },
      onUnknownEvent: (type) => addClientError(`Ignored unknown WebSocket event: ${type}`),
    });
    void refresh();
    socket.connect();
    return () => {
      mounted.current = false;
      socket.close();
    };
  }, [addClientError, refresh]);

  const updateWith = useCallback(async <T,>(operation: () => Promise<T>): Promise<T> => {
    try {
      return await operation();
    } catch (error) {
      if (isNetworkError(error)) {
        setView((current) => ({ ...current, coreStatus: "offline", stale: true }));
      }
      throw error;
    }
  }, []);

  const updateConfig = useCallback(
    (patch: ConfigPatch) =>
      updateWith(async () => {
        const config = await api.updateConfig(patch);
        setView((current) => ({ ...current, config }));
        return config;
      }),
    [updateWith],
  );

  const setRumble = useCallback(
    (enabled: boolean) =>
      updateWith(async () => {
        const runtime = await api.setRumble(enabled);
        setView((current) => ({
          ...current,
          runtime,
          stale: stateIsStale(current.coreStatus, runtime),
        }));
        return runtime;
      }),
    [updateWith],
  );

  const setTouchpad = useCallback(
    (enabled: boolean) =>
      updateWith(async () => {
        const runtime = await api.setTouchpad(enabled);
        setView((current) => ({
          ...current,
          runtime,
          stale: stateIsStale(current.coreStatus, runtime),
        }));
        return runtime;
      }),
    [updateWith],
  );

  const testRumble = useCallback(
    (payload?: { left?: number; right?: number; duration_ms?: number }) =>
      updateWith(async () => (await api.testRumble(payload)).accepted),
    [updateWith],
  );

  const loadControllerProfile = useCallback(
    (name: string) =>
      updateWith(async () => {
        const response = await api.loadProfile(name);
        setView((current) => ({
          ...current,
          config: response.config,
          runtime: response.state ?? current.runtime,
        }));
        await refresh();
        return response;
      }),
    [refresh, updateWith],
  );

  const loadProfile = useCallback(
    (name: string) => loadControllerProfile(name).then((response) => response.config),
    [loadControllerProfile],
  );

  const saveProfile = useCallback(
    (name: string, rumble: Partial<Config["rumble"]>) =>
      updateWith(async () => {
        await api.saveProfile(name, rumble);
        const profiles = await api.profiles();
        setView((current) => ({ ...current, profiles: profiles.profiles }));
      }),
    [updateWith],
  );

  const deleteProfile = useCallback(
    (name: string) =>
      updateWith(async () => {
        await api.deleteProfile(name);
        const profiles = await api.profiles();
        setView((current) => ({ ...current, profiles: profiles.profiles }));
      }),
    [updateWith],
  );

  const applyLightbar = useCallback(
    (state: LightbarState) =>
      updateWith(async () => {
        const lightbar = await api.applyLightbar(state);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, lightbar } : current.runtime,
        }));
        return lightbar;
      }),
    [updateWith],
  );

  const resetLightbar = useCallback(
    () =>
      updateWith(async () => {
        const lightbar = await api.resetLightbar();
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, lightbar } : current.runtime,
        }));
        return lightbar;
      }),
    [updateWith],
  );

  const applyPlayerLeds = useCallback(
    (state: PlayerLedState) =>
      updateWith(async () => {
        const player_leds = await api.applyPlayerLeds(state);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, player_leds } : current.runtime,
        }));
        return player_leds;
      }),
    [updateWith],
  );

  const resetPlayerLeds = useCallback(
    () =>
      updateWith(async () => {
        const player_leds = await api.resetPlayerLeds();
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, player_leds } : current.runtime,
        }));
        return player_leds;
      }),
    [updateWith],
  );

  const applyTriggers = useCallback(
    (state: { left: TriggerEffect; right: TriggerEffect }) =>
      updateWith(async () => {
        const triggers = await api.applyTriggers(state);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, triggers } : current.runtime,
        }));
        return triggers;
      }),
    [updateWith],
  );

  const previewTriggers = useCallback(
    (state: { left: TriggerEffect; right: TriggerEffect }, durationMs: number) =>
      updateWith(async () => {
        const preview = await api.previewTriggers({ ...state, duration_ms: durationMs });
        setView((current) => ({
          ...current,
          runtime: current.runtime
            ? { ...current.runtime, triggers: { ...state, preview } }
            : current.runtime,
        }));
        return preview;
      }),
    [updateWith],
  );

  const cancelTriggerPreview = useCallback(
    () =>
      updateWith(async () => {
        const preview = await api.cancelTriggerPreview();
        setView((current) => ({
          ...current,
          runtime: current.runtime
            ? {
                ...current.runtime,
                triggers: { ...(current.runtime.triggers ?? EMPTY_TRIGGERS), preview },
              }
            : current.runtime,
        }));
        return preview;
      }),
    [updateWith],
  );

  const resetTriggers = useCallback(
    () =>
      updateWith(async () => {
        const triggers = await api.resetTriggers();
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, triggers } : current.runtime,
        }));
        return triggers;
      }),
    [updateWith],
  );

  const startHapticsTest = useCallback(
    (payload: { left: number; right: number; duration_ms: number }) =>
      updateWith(async () => {
        const run = await api.startHapticsTest(payload);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, haptics_test: run } : current.runtime,
        }));
        return run;
      }),
    [updateWith],
  );

  const cancelHapticsTest = useCallback(
    () =>
      updateWith(async () => {
        const run = await api.cancelHapticsTest();
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, haptics_test: run } : current.runtime,
        }));
        return run;
      }),
    [updateWith],
  );

  const updateStickCalibration = useCallback(
    (calibration: StickCalibration) =>
      updateWith(async () => {
        const sticks = await api.updateStickCalibration(calibration);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, stick_calibration: sticks } : current.runtime,
        }));
        return sticks;
      }),
    [updateWith],
  );

  const estimateStickCalibration = useCallback(
    (samples: StickTelemetry[]) => updateWith(() => api.estimateStickCalibration(samples)),
    [updateWith],
  );

  const updateGestures = useCallback(
    (patch: Partial<GestureConfig>) =>
      updateWith(async () => {
        const gestureConfig = await api.updateGestures(patch);
        setView((current) => ({
          ...current,
          runtime: current.runtime ? { ...current.runtime, gesture_config: gestureConfig } : current.runtime,
          config: current.config
            ? {
                ...current.config,
                trackpad: {
                  ...current.config.trackpad,
                  gestures_enabled: gestureConfig.enabled,
                  two_finger_scroll: gestureConfig.two_finger_scroll,
                  tap_to_click: gestureConfig.tap_to_click,
                  swipe_enabled: gestureConfig.swipe_enabled,
                  swipe_threshold: gestureConfig.swipe_threshold,
                },
              }
            : current.config,
        }));
        return gestureConfig;
      }),
    [updateWith],
  );

  const saveControllerProfile = useCallback(
    (name: string, profile: ControllerProfile, confirmOverwrite = false) =>
      updateWith(async () => {
        const response = await api.saveControllerProfile(name, profile, confirmOverwrite);
        const profiles = await api.profiles();
        setView((current) => ({ ...current, profiles: profiles.profiles }));
        return response;
      }),
    [updateWith],
  );

  const exportProfile = useCallback((name: string) => updateWith(() => api.getProfile(name)), [updateWith]);

  const importProfile = useCallback(
    (content: string, name?: string, confirmOverwrite = false) =>
      updateWith(async () => {
        const profile = await api.importProfile(content, name, confirmOverwrite);
        const profiles = await api.profiles();
        setView((current) => ({ ...current, profiles: profiles.profiles }));
        return profile;
      }),
    [updateWith],
  );

  const value = useMemo<RuntimeContextValue>(
    () => ({
      ...view,
      refresh,
      updateConfig,
      setRumble,
      setTouchpad,
      testRumble,
      loadProfile,
      loadControllerProfile,
      saveProfile,
      saveControllerProfile,
      exportProfile,
      importProfile,
      deleteProfile,
      applyLightbar,
      resetLightbar,
      applyPlayerLeds,
      resetPlayerLeds,
      applyTriggers,
      previewTriggers,
      cancelTriggerPreview,
      resetTriggers,
      startHapticsTest,
      cancelHapticsTest,
      updateStickCalibration,
      estimateStickCalibration,
      updateGestures,
      canControl: view.coreStatus === "online" && !view.stale && view.runtime?.connection === "connected",
    }),
    [
      applyLightbar,
      applyPlayerLeds,
      applyTriggers,
      cancelHapticsTest,
      cancelTriggerPreview,
      deleteProfile,
      exportProfile,
      importProfile,
      loadProfile,
      loadControllerProfile,
      previewTriggers,
      refresh,
      saveProfile,
      saveControllerProfile,
      resetLightbar,
      resetPlayerLeds,
      resetTriggers,
      setRumble,
      setTouchpad,
      startHapticsTest,
      testRumble,
      updateConfig,
      updateGestures,
      updateStickCalibration,
      estimateStickCalibration,
      view,
    ],
  );

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
}

export function useRuntime(): RuntimeContextValue {
  const value = useContext(RuntimeContext);
  if (!value) throw new Error("useRuntime must be used inside RuntimeProvider");
  return value;
}

export function controllerLabel(runtime: RuntimeState | null, stale: boolean): string {
  if (!runtime) return "Waiting for controller";
  if (stale) return `Stale · ${runtime.connection}`;
  return runtime.connection;
}

export function formatRuntimeError(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  return errorMessage(error);
}
