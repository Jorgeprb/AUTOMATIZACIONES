import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { LoadingState } from "@/components/common/LoadingState";

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const ClinicsPage = lazy(() =>
  import("@/pages/ClinicsPage").then((module) => ({
    default: module.ClinicsPage,
  })),
);
const ClinicDetailPage = lazy(() =>
  import("@/pages/ClinicDetailPage").then((module) => ({
    default: module.ClinicDetailPage,
  })),
);
const WorkersPage = lazy(() =>
  import("@/pages/WorkersPage").then((module) => ({
    default: module.WorkersPage,
  })),
);
const ServicesPage = lazy(() =>
  import("@/pages/ServicesPage").then((module) => ({
    default: module.ServicesPage,
  })),
);
const AssistantConfigPage = lazy(() =>
  import("@/pages/AssistantConfigPage").then((module) => ({
    default: module.AssistantConfigPage,
  })),
);
const FlowEditorPage = lazy(() =>
  import("@/pages/FlowEditorPage").then((module) => ({
    default: module.FlowEditorPage,
  })),
);
const KnowledgePage = lazy(() =>
  import("@/pages/KnowledgePage").then((module) => ({
    default: module.KnowledgePage,
  })),
);
const ConversationsPage = lazy(() =>
  import("@/pages/ConversationsPage").then((module) => ({
    default: module.ConversationsPage,
  })),
);
const ConversationDetailPage = lazy(() =>
  import("@/pages/ConversationDetailPage").then((module) => ({
    default: module.ConversationDetailPage,
  })),
);
const CalendarPage = lazy(() =>
  import("@/pages/CalendarPage").then((module) => ({
    default: module.CalendarPage,
  })),
);
const TestConsolePage = lazy(() =>
  import("@/pages/TestConsolePage").then((module) => ({
    default: module.TestConsolePage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

export default function App() {
  return (
    <Suspense fallback={<div className="p-8"><LoadingState rows={6} /></div>}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="clinics" element={<ClinicsPage />} />
          <Route path="clinics/:clinicId" element={<ClinicDetailPage />} />
          <Route path="clinics/:clinicId/workers" element={<WorkersPage />} />
          <Route path="clinics/:clinicId/services" element={<ServicesPage />} />
          <Route
            path="clinics/:clinicId/assistant"
            element={<AssistantConfigPage />}
          />
          <Route path="clinics/:clinicId/flows" element={<FlowEditorPage />} />
          <Route
            path="clinics/:clinicId/knowledge"
            element={<KnowledgePage />}
          />
          <Route
            path="clinics/:clinicId/conversations"
            element={<ConversationsPage />}
          />
          <Route
            path="clinics/:clinicId/conversations/:callId"
            element={<ConversationDetailPage />}
          />
          <Route path="clinics/:clinicId/calendar" element={<CalendarPage />} />
          <Route path="clinics/:clinicId/test" element={<TestConsolePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
