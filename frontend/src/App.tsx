import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { LoadingState } from "@/components/common/LoadingState";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { isAdminPortal } from "@/lib/portal";

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
const ClientAccountsPage = lazy(() =>
  import("@/pages/ClientAccountsPage").then((module) => ({
    default: module.ClientAccountsPage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const CustomersPage = lazy(() => import("@/pages/CustomersPage").then((module) => ({ default: module.CustomersPage })));
const ResourcesPage = lazy(() => import("@/pages/ResourcesPage").then((module) => ({ default: module.ResourcesPage })));
const StatisticsPage = lazy(() => import("@/pages/StatisticsPage").then((module) => ({ default: module.StatisticsPage })));
const PurchasesPage = lazy(() => import("@/pages/PurchasesPage").then((module) => ({ default: module.PurchasesPage })));
const RegisterPage = lazy(() => import("@/pages/RegisterPage").then((module) => ({ default: module.RegisterPage })));
const OnboardingPage = lazy(() => import("@/pages/OnboardingPage").then((module) => ({ default: module.OnboardingPage })));
const BusinessAdminPage = lazy(() => import("@/pages/BusinessAdminPage").then((module) => ({ default: module.BusinessAdminPage })));
const CommercialAccountPage = lazy(() => import("@/pages/CommercialAccountPage").then((module) => ({ default: module.CommercialAccountPage })));
const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((module) => ({
    default: module.LoginPage,
  })),
);

export default function App() {
  return (
    <Suspense fallback={<div className="p-8"><LoadingState rows={6} /></div>}>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="clinics" element={<ClinicsPage />} />
            <Route path="clinics/:clinicId" element={<ClinicDetailPage />} />
            <Route path="clinics/:clinicId/workers" element={<WorkersPage />} />
            <Route path="clinics/:clinicId/customers" element={<CustomersPage />} />
            <Route path="clinics/:clinicId/resources" element={<ResourcesPage />} />
            <Route path="clinics/:clinicId/statistics" element={<StatisticsPage />} />
            <Route path="clinics/:clinicId/purchases" element={<PurchasesPage />} />
            <Route
              path="clinics/:clinicId/services"
              element={<ServicesPage />}
            />
            <Route
              path="clinics/:clinicId/assistant"
              element={<AssistantConfigPage />}
            />
            <Route
              path="clinics/:clinicId/flows"
              element={<FlowEditorPage />}
            />
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
            <Route
              path="clinics/:clinicId/calendar"
              element={<CalendarPage />}
            />
            <Route
              path="clinics/:clinicId/test"
              element={<TestConsolePage />}
            />
            <Route path="users" element={isAdminPortal ? <ClientAccountsPage /> : <Navigate to="/" replace />} />
            <Route path="business" element={isAdminPortal ? <BusinessAdminPage /> : <Navigate to="/" replace />} />
            <Route path="onboarding" element={<OnboardingPage />} />
            <Route path="account" element={<CommercialAccountPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
