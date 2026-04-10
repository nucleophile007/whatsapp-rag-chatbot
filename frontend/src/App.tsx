import { Suspense, lazy } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const ExecutionLogs = lazy(() => import("./pages/ExecutionLogs"));
const KnowledgeBase = lazy(() => import("./pages/KnowledgeBase"));
const Workspaces = lazy(() => import("./pages/Workspaces"));
const WorkspaceDetail = lazy(() => import("./pages/WorkspaceDetail"));
const LogicLayers = lazy(() => import("./pages/LogicLayers"));
const FlowBuilder = lazy(() => import("./pages/FlowBuilder"));
const MemoryDebug = lazy(() => import("./pages/MemoryDebug"));

function PageLoader() {
  return (
    <div className="flex h-full min-h-[320px] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="executions" element={<ExecutionLogs />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="memory" element={<MemoryDebug />} />
          <Route path="workspaces" element={<Workspaces />} />
          <Route path="workspaces/:id" element={<WorkspaceDetail />} />
          <Route path="logic-layers" element={<LogicLayers />} />
          <Route path="flows/:id" element={<FlowBuilder />} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default App;
