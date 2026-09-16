import {
  Activity,
  AudioWaveform,
  CircleHelp,
  Gamepad2,
  Gamepad,
  Gauge,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Touchpad,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { StatusPill } from "../ui";
import { controllerLabel, useRuntime } from "../../lib/runtime/RuntimeProvider";
import { useI18n, type TranslationKey } from "../../lib/i18n";

const navigation: ReadonlyArray<{ to: string; labelKey: TranslationKey; icon: LucideIcon }> = [
  { to: "/", labelKey: "nav.overview", icon: Gauge },
  { to: "/haptics", labelKey: "nav.haptics", icon: AudioWaveform },
  { to: "/touchpad", labelKey: "nav.touchpad", icon: Touchpad },
  { to: "/controller", labelKey: "nav.controller", icon: Gamepad2 },
  { to: "/games", labelKey: "nav.games", icon: Gamepad },
  { to: "/profiles", labelKey: "nav.profiles", icon: SlidersHorizontal },
  { to: "/diagnostics", labelKey: "nav.diagnostics", icon: Activity },
  { to: "/settings", labelKey: "nav.settings", icon: Settings },
];

function coreTone(status: string): "success" | "warning" | "danger" | "neutral" {
  if (status === "online") return "success";
  if (status === "reconnecting") return "warning";
  if (status === "protocol_error") return "danger";
  return "neutral";
}

function controllerTone(
  connection: string | undefined,
  stale: boolean,
): "success" | "warning" | "danger" | "neutral" {
  if (stale || !connection) return "neutral";
  if (connection === "connected") return "success";
  if (connection === "error") return "danger";
  if (connection === "connecting" || connection === "reconnecting") return "warning";
  return "neutral";
}

export function AppShell() {
  const { coreStatus, runtime, stale, clientErrors } = useRuntime();
  const { t } = useI18n();
  const coreLabel =
    coreStatus === "protocol_error"
      ? t("shell.protocolError")
      : coreStatus === "online"
        ? t("status.coreOnline")
        : coreStatus === "reconnecting"
          ? t("status.coreReconnecting")
          : t("status.coreOffline");
  const controller = controllerLabel(runtime, stale);
  const trustedRuntime = stale ? null : runtime;
  const activeProfile = trustedRuntime?.automation?.active_profile ?? trustedRuntime?.active_profile;
  const profileOrigin = trustedRuntime?.automation?.profile_origin;
  const mode = trustedRuntime?.exclusive?.enabled
    ? t("shell.modeExclusive")
    : trustedRuntime?.compatibility?.mode === "remap"
      ? t("shell.modeRemap")
      : t("shell.modeNative");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={17} />
          </div>
          <div>
            <strong>DS5Forge</strong>
            <span>{t("shell.wiredCompanion")}</span>
          </div>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map(({ to, labelKey, icon: Icon }) => (
            <NavLink
              key={labelKey}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <CircleHelp size={15} />
          <span>{t("shell.usbLocalOnly")}</span>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="mobile-brand">
            <div className="brand-mark">
              <Sparkles size={15} />
            </div>
            <strong>DS5Forge</strong>
          </div>
          <div className="global-status" aria-label="Service and controller status">
            <StatusPill tone={coreTone(coreStatus)} label={coreLabel} />
            <StatusPill
              tone={controllerTone(runtime?.connection, stale)}
              label={stale ? t("status.controllerStale") : controller}
              detail={trustedRuntime?.identity?.transport === "usb" ? t("status.usb") : undefined}
            />
            <div className="topbar-context" aria-label="Active profile, origin and mode">
              <span>{`${t("shell.profile")}: ${activeProfile ?? "—"}`}</span>
              <span>{`${t("shell.origin")}: ${profileOrigin ?? "—"}`}</span>
              <span>{`${t("shell.mode")}: ${stale ? "—" : mode}`}</span>
            </div>
          </div>
        </header>
        {coreStatus !== "online" && (
          <div
            className={`global-banner ${coreStatus === "protocol_error" ? "banner-danger" : "banner-warning"}`}
            role="status"
          >
            <strong>{coreLabel}</strong>
            <span>
              {coreStatus === "protocol_error" ? t("shell.coreUntrusted") : t("shell.coreUnavailable")}
            </span>
          </div>
        )}
        {clientErrors.length > 0 && (
          <div className="client-error-strip" role="status">
            <span>{clientErrors[0]}</span>
            <NavLink to="/diagnostics">{t("shell.viewDiagnostics")}</NavLink>
          </div>
        )}
        <main className="content">
          <Outlet />
        </main>
        <nav className="mobile-nav" aria-label="Compact navigation">
          {navigation.map(({ to, labelKey, icon: Icon }) => (
            <NavLink
              key={labelKey}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `mobile-nav-item${isActive ? " active" : ""}`}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
