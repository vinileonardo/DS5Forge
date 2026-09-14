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
  type HealthResponse,
  type ProfileSummary,
  type RuntimeState,
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
  saveProfile: (name: string, rumble: Partial<NonNullable<Config>["rumble"]>) => Promise<void>;
  deleteProfile: (name: string) => Promise<void>;
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
    setView((current) => ({
      ...current,
      health: healthResult.status === "fulfilled" ? healthResult.value : current.health,
      runtime: stateResult.status === "fulfilled" ? stateResult.value : current.runtime,
      config: configResult.status === "fulfilled" ? configResult.value : current.config,
      profiles: profilesResult.status === "fulfilled" ? profilesResult.value.profiles : current.profiles,
      coreStatus: networkFailure || stateResult.status === "rejected" ? "offline" : current.coreStatus,
      loading: false,
      stale: networkFailure || stateResult.status === "rejected" || current.coreStatus !== "online",
    }));
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
          stale: status !== "online",
          reconnectAttempt: socket.reconnectAttempt,
          loading: false,
        }));
      },
      onEvent: (event) => {
        if (!mounted.current) return;
        setView((current) => {
          const projection = applyRuntimeEvent(current, event);
          const entry = sessionEventFor(event, ++nextEventId.current);
          return {
            ...current,
            ...projection,
            events: [entry, ...current.events].slice(0, 50),
            stale: false,
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
        setView((current) => ({ ...current, runtime, stale: false }));
        return runtime;
      }),
    [updateWith],
  );

  const setTouchpad = useCallback(
    (enabled: boolean) =>
      updateWith(async () => {
        const runtime = await api.setTouchpad(enabled);
        setView((current) => ({ ...current, runtime, stale: false }));
        return runtime;
      }),
    [updateWith],
  );

  const testRumble = useCallback(
    (payload?: { left?: number; right?: number; duration_ms?: number }) =>
      updateWith(async () => (await api.testRumble(payload)).accepted),
    [updateWith],
  );

  const loadProfile = useCallback(
    (name: string) =>
      updateWith(async () => {
        const response = await api.loadProfile(name);
        setView((current) => ({ ...current, config: response.config }));
        await refresh();
        return response.config;
      }),
    [refresh, updateWith],
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

  const value = useMemo<RuntimeContextValue>(
    () => ({
      ...view,
      refresh,
      updateConfig,
      setRumble,
      setTouchpad,
      testRumble,
      loadProfile,
      saveProfile,
      deleteProfile,
      canControl: view.coreStatus === "online" && view.runtime?.connection === "connected",
    }),
    [
      deleteProfile,
      loadProfile,
      refresh,
      saveProfile,
      setRumble,
      setTouchpad,
      testRumble,
      updateConfig,
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
