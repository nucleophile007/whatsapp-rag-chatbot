import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getWorkspaces, createWorkspace, getCollections, setWorkspaceStatus } from "../lib/api";
import {
  Loader2,
  Plus,
  Bot,
  Save,
  ChevronRight,
  Atom,
  Power,
  Layers,
  CircleDot,
  PauseCircle,
  PlayCircle,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useNavigate } from "react-router-dom";
import type {
  Collection,
  WorkspaceDetailResponse,
  WorkspaceFormInput,
  WorkspacesResponse,
  WorkspaceSummary,
} from "../lib/types";

const defaultForm: WorkspaceFormInput = {
  name: "",
  knowledge_base_id: "",
  system_prompt: "You are a helpful assistant. Use the following context to answer questions.",
  user_prompt_template: "Question: {{body}}\n\nContext: {{rag_result}}",
  low_quality_clarification_text: "",
  contact_filter_mode: "all",
  contact_chat_ids: [],
  group_ids: [],
};

export default function Workspaces() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState<WorkspaceFormInput>(defaultForm);

  const { data: workspacesData, isLoading: wsLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: getWorkspaces,
  });

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
  });

  const createMutation = useMutation({
    mutationFn: createWorkspace,
    onSuccess: (newWs) => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setIsCreating(false);
      setFormData(defaultForm);
      if (newWs?.id) navigate(`/workspaces/${newWs.id}`);
    },
  });

  const statusMutation = useMutation({
    mutationFn: setWorkspaceStatus,
    onMutate: async ({ id, is_active }) => {
      await queryClient.cancelQueries({ queryKey: ["workspaces"] });
      const previousWorkspaces = queryClient.getQueryData<WorkspacesResponse>(["workspaces"]);
      const previousWorkspaceDetail = queryClient.getQueryData<WorkspaceDetailResponse>(["workspace", id]);

      queryClient.setQueryData<WorkspacesResponse>(["workspaces"], (current) => {
        if (!current) return current;
        return {
          ...current,
          workspaces: current.workspaces.map((workspace) =>
            workspace.id === id ? { ...workspace, is_active } : workspace
          ),
        };
      });

      queryClient.setQueryData<WorkspaceDetailResponse>(["workspace", id], (current) =>
        current ? { ...current, is_active } : current
      );

      return { previousWorkspaces, previousWorkspaceDetail, workspaceId: id };
    },
    onError: (_error, _variables, context) => {
      if (context?.previousWorkspaces) {
        queryClient.setQueryData(["workspaces"], context.previousWorkspaces);
      }
      if (context?.previousWorkspaceDetail && context.workspaceId) {
        queryClient.setQueryData(["workspace", context.workspaceId], context.previousWorkspaceDetail);
      }
    },
    onSuccess: ({ workspace_id, is_active }) => {
      queryClient.setQueryData<WorkspacesResponse>(["workspaces"], (current) => {
        if (!current) return current;
        return {
          ...current,
          workspaces: current.workspaces.map((workspace) =>
            workspace.id === workspace_id ? { ...workspace, is_active } : workspace
          ),
        };
      });
      queryClient.setQueryData<WorkspaceDetailResponse>(["workspace", workspace_id], (current) =>
        current ? { ...current, is_active } : current
      );
    },
  });

  if (wsLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  const workspaces = workspacesData?.workspaces || [];
  const collections = collectionsData?.collections || [];
  const pendingWorkspaceId = statusMutation.variables?.id;

  return (
    <div className="mx-auto max-w-7xl space-y-7 p-5 md:p-8">
      <section className="panel animate-rise flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div className="page-header">
          <p className="tag bg-secondary text-secondary-foreground">
            <Layers className="h-3.5 w-3.5" />
            AI Environments
          </p>
          <h1 className="title-xl">Workspaces</h1>
          <p className="subtitle">Configure prompts, attach a knowledge base, and route behavior to WhatsApp groups.</p>
        </div>

        {!isCreating && (
          <button
            onClick={() => {
              setFormData(defaultForm);
              setIsCreating(true);
            }}
            className="btn-primary w-fit"
          >
            <Plus className="h-4 w-4" />
            New Workspace
          </button>
        )}
      </section>

      {isCreating && (
        <section className="panel animate-rise p-6 md:p-8">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-2xl font-bold">Create Workspace</h2>
              <p className="subtitle">Set baseline behavior and knowledge source.</p>
            </div>
            <button onClick={() => setIsCreating(false)} className="btn-secondary">
              Cancel
            </button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Name</span>
              <input
                value={formData.name}
                onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="Customer Support Bot"
                className="input-base"
              />
            </label>

            <label className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Knowledge Base</span>
              <select
                value={formData.knowledge_base_id}
                onChange={(e) => setFormData((prev) => ({ ...prev, knowledge_base_id: e.target.value }))}
                className="input-base"
              >
                <option value="">No Knowledge Base (LLM only)</option>
                {collections.map((collection: Collection) => (
                  <option key={collection.id} value={collection.id}>
                    {collection.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            onClick={() => createMutation.mutate(formData)}
            disabled={createMutation.isPending || !formData.name.trim()}
            className="btn-primary mt-6 w-full md:w-auto"
          >
            {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {createMutation.isPending ? "Creating..." : "Create Workspace"}
          </button>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {workspaces.map((workspace: WorkspaceSummary, index: number) => (
          <article
            key={workspace.id}
            style={{ animationDelay: `${index * 70}ms` }}
            className="panel animate-rise group p-5 transition-all hover:-translate-y-1 hover:shadow-lg"
          >
            <div className="mb-4 flex items-start justify-between">
              <div className="rounded-2xl bg-secondary p-3 text-primary">
                <Bot className="h-5 w-5" />
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "tag",
                    workspace.is_active
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 bg-slate-50 text-slate-500"
                  )}
                >
                  <CircleDot className={cn("h-3 w-3", workspace.is_active && "animate-pulse")} />
                  {workspace.is_active ? "Active" : "Paused"}
                </span>
                <button
                  onClick={(event) => {
                    event.stopPropagation();
                    statusMutation.mutate({ id: workspace.id, is_active: !workspace.is_active });
                  }}
                  disabled={statusMutation.isPending && pendingWorkspaceId === workspace.id}
                  className="btn-secondary px-3 py-1.5 text-xs"
                >
                  {statusMutation.isPending && pendingWorkspaceId === workspace.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : workspace.is_active ? (
                    <PauseCircle className="h-3.5 w-3.5" />
                  ) : (
                    <PlayCircle className="h-3.5 w-3.5" />
                  )}
                  {workspace.is_active ? "Pause" : "Activate"}
                </button>
              </div>
            </div>

            <h3 className="text-xl font-bold group-hover:text-primary">{workspace.name}</h3>

            <p className="mt-1 text-sm text-muted-foreground">
              {workspace.knowledge_base ? `KB: ${workspace.knowledge_base.name}` : "No knowledge base attached"}
            </p>

            <div className="mt-5 flex min-h-[34px] flex-wrap gap-1.5">
              {workspace.groups?.length > 0 ? (
                workspace.groups.slice(0, 4).map((group) => (
                  <span key={group.id} className="tag border-slate-200 bg-slate-50 text-slate-600">
                    #{group.name}
                  </span>
                ))
              ) : (
                <span className="text-xs italic text-muted-foreground">No groups connected</span>
              )}
              {workspace.groups?.length > 4 && (
                <span className="tag border-slate-200 bg-slate-50 text-slate-600">+{workspace.groups.length - 4}</span>
              )}
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-dashed pt-4 text-sm font-semibold text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Atom className="h-3.5 w-3.5" />
                Workspace Detail
              </span>
              <button
                onClick={() => navigate(`/workspaces/${workspace.id}`)}
                className="btn-secondary px-3 py-1.5 text-xs"
              >
                Open
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </article>
        ))}
      </section>

      {workspaces.length > 0 && (
        <p className="px-1 text-xs text-muted-foreground">
          Workspace activation is independent per workspace. If multiple active workspaces share a group, each one can execute.
        </p>
      )}

      {workspaces.length === 0 && !isCreating && (
        <section className="panel-muted animate-rise flex flex-col items-center gap-3 p-12 text-center">
          <Power className="h-10 w-10 text-muted-foreground" />
          <h3 className="text-xl font-bold">No workspaces yet</h3>
          <p className="subtitle max-w-md">Create your first workspace to define RAG behavior and attach it to group conversations.</p>
          <button
            onClick={() => {
              setFormData(defaultForm);
              setIsCreating(true);
            }}
            className="btn-primary"
          >
            <Plus className="h-4 w-4" />
            Create First Workspace
          </button>
        </section>
      )}
    </div>
  );
}
