// Saari routing yahan se handle hoti hai bhai
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ExecutionLogs from "./pages/ExecutionLogs";
import KnowledgeBase from "./pages/KnowledgeBase";
import Workspaces from "./pages/Workspaces";
import WorkspaceDetail from "./pages/WorkspaceDetail";
import FlowBuilder from "./pages/FlowBuilder";


function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="executions" element={<ExecutionLogs />} />
        <Route path="knowledge-base" element={<KnowledgeBase />} />
        <Route path="workspaces" element={<Workspaces />} />
        <Route path="workspaces/:id" element={<WorkspaceDetail />} />
        <Route path="flows/:id" element={<FlowBuilder />} />
      </Route>
    </Routes>
  );
}

export default App;
