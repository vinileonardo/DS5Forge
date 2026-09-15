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

const navigation: ReadonlyArray<{ to: string; label: string; icon: LucideIcon }> = [
  { to: "/", label: "Overview", icon: Gauge },
  { to: "/haptics", label: "Haptics", icon: AudioWaveform },
  { to: "/touchpad", label: "Touchpad", icon: Touchpad },
  { to: "/controller", label: "Controller Lab", icon: Gamepad2 },
  { to: "/games", label: "Games", icon: Gamepad },
  { to: "/profiles", label: "Profiles", icon: SlidersHorizontal },
  { to: "/diagnostics", label: "Diagnostics", icon: Activity },
  { to: "/settings", label: "Settings", icon: Settings },
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
  const coreLabel =
    coreStatus === "protocol_error"
      ? "Protocol error"
      : coreStatus === "online"
        ? "Local core online"
        : coreStatus === "reconnecting"
          ? "Reconnecting"
          : "Local core offline";
  const controller = controllerLabel(runtime, stale);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={17} />
          </div>
          <div>
            <strong>DS5Forge</strong>
            <span>Wired companion</span>
          </div>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={label}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <CircleHelp size={15} />
          <span>USB / local only</span>
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
              label={stale ? "Controller state stale" : controller}
              detail={runtime?.identity?.transport === "usb" ? "USB" : undefined}
            />
          </div>
        </header>
        {coreStatus !== "online" && (
          <div
            className={`global-banner ${coreStatus === "protocol_error" ? "banner-danger" : "banner-warning"}`}
            role="status"
          >
            <strong>{coreLabel}</strong>
            <span>
              {coreStatus === "protocol_error"
                ? "The core returned data the client could not trust. Check Diagnostics."
                : "Start the core with `python source/run.py --headless`; this UI will retry automatically."}
            </span>
          </div>
        )}
        {clientErrors.length > 0 && (
          <div className="client-error-strip" role="status">
            <span>{clientErrors[0]}</span>
            <NavLink to="/diagnostics">View diagnostics</NavLink>
          </div>
        )}
        <main className="content">
          <Outlet />
        </main>
        <nav className="mobile-nav" aria-label="Compact navigation">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={label}
              to={to}
              end={to === "/"}
              className={({ isActive }) => `mobile-nav-item${isActive ? " active" : ""}`}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
