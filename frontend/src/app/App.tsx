import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/layout/AppShell";
import { DiagnosticsPage } from "../features/diagnostics/DiagnosticsPage";
import { ControllerLabPage } from "../features/controller/ControllerLabPage";
import { HapticsPage } from "../features/haptics/HapticsPage";
import { GamesPage } from "../features/games/GamesPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { ProfilesPage } from "../features/profiles/ProfilesPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TouchpadPage } from "../features/touchpad/TouchpadPage";
import { useRuntime } from "../lib/runtime/RuntimeProvider";
import { I18nProvider } from "../lib/i18n";

function ThemeSynchronizer() {
  const { config } = useRuntime();
  useEffect(() => {
    if (!config?.theme) return;
    document.documentElement.dataset.theme = config.theme;
    try {
      localStorage.setItem("ds5forge.theme", config.theme);
    } catch {
      // The inline bootstrap remains authoritative for first paint in a
      // restricted/offline shell.
    }
  }, [config?.theme]);
  return null;
}

function RoutedApp() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="haptics" element={<HapticsPage />} />
        <Route path="touchpad" element={<TouchpadPage />} />
        <Route path="controller" element={<ControllerLabPage />} />
        <Route path="games" element={<GamesPage />} />
        <Route path="profiles" element={<ProfilesPage />} />
        <Route path="diagnostics" element={<DiagnosticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <I18nProvider>
      <ThemeSynchronizer />
      <RoutedApp />
    </I18nProvider>
  );
}
