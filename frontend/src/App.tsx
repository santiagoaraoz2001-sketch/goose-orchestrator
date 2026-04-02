import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/Layout/AppShell";
import DashboardView from "./views/DashboardView";
import ModelsView from "./views/ModelsView";
import WorkersView from "./views/WorkersView";
import SettingsView from "./views/SettingsView";
import StatusView from "./views/StatusView";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardView />} />
        <Route path="/models" element={<ModelsView />} />
        <Route path="/workers" element={<WorkersView />} />
        <Route path="/settings" element={<SettingsView />} />
        <Route path="/status" element={<StatusView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
