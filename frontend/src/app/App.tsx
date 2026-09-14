import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/layout/AppShell";
import { DiagnosticsPage } from "../features/diagnostics/DiagnosticsPage";
import { HapticsPage } from "../features/haptics/HapticsPage";
import { OverviewPage } from "../features/overview/OverviewPage";
import { ProfilesPage } from "../features/profiles/ProfilesPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TouchpadPage } from "../features/touchpad/TouchpadPage";
import { useRuntime } from "../lib/runtime/RuntimeProvider";

function ThemeSynchronizer() {
  const { config } = useRuntime();
  useEffect(() => {
    document.documentElement.dataset.theme = config?.theme ?? "Dark";
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
    <>
      <ThemeSynchronizer />
      <RoutedApp />
    </>
  );
}
