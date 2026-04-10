import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Search, Workflow, Loader2, Plus, Trash2 } from "lucide-react";
import { createFlow, deleteFlow, getFlows } from "../lib/api";
import type { FlowCreateInput, FlowSummary } from "../lib/types";

const getNextLogicLayerName = (flows: FlowSummary[]): string => {
  const normalized = new Set(flows.map((flow) => flow.name.trim().toLowerCase()));
  let index = 1;
  while (normalized.has(`logic layer ${index}`.toLowerCase())) {
    index += 1;
  }
  return `Logic Layer ${index}`;
};

export default function LogicLayers() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [newFlowName, setNewFlowName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["flows", "all"],
    queryFn: () => getFlows(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: FlowCreateInput) => createFlow(payload),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      if (result.flow_id) {
        navigate(`/flows/${result.flow_id}`);
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFlow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows"] });
      queryClient.invalidateQueries({ queryKey: ["workspace"] });
    },
  });

  const flows = useMemo(() => data?.flows ?? [], [data?.flows]);
  const suggestedFlowName = useMemo(() => getNextLogicLayerName(flows), [flows]);
  const deletingFlowId = deleteMutation.variables;

  const filteredFlows = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return flows.filter((flow) => {
      if (!normalizedSearch) return true;
      return (
        flow.name.toLowerCase().includes(normalizedSearch) ||
        (flow.description || "").toLowerCase().includes(normalizedSearch) ||
        flow.trigger_type.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [flows, search]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  const handleCreate = () => {
    const flowName = newFlowName.trim() || suggestedFlowName;
    const payload: FlowCreateInput = {
      name: flowName,
      trigger_type: "whatsapp_message",
      trigger_config: {},
      definition: {
        nodes: [
          {
            id: "start",
            type: "trigger",
            data: { label: "Incoming Message", type: "trigger", subType: "whatsapp_message", config: {} },
            position: { x: 0, y: 0 },
          },
        ],
        edges: [],
      },
    };
    createMutation.mutate(payload);
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
      <section className="panel animate-rise flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div className="page-header">
          <p className="tag bg-secondary text-secondary-foreground">
            <Workflow className="h-3.5 w-3.5" />
            Automation Catalog
          </p>
          <h1 className="title-xl">Logic Layers</h1>
          <p className="subtitle">All logic layers in one place. Open any item to edit in Flow Builder. Workspace active/paused state is managed in Workspace page.</p>
        </div>
      </section>

      <section className="panel animate-rise p-4 md:p-5">
        <div className="mb-3 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          <Plus className="h-3.5 w-3.5" />
          Add New Logic Layer
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <input
            value={newFlowName}
            onChange={(event) => setNewFlowName(event.target.value)}
            className="input-base"
            placeholder={`Logic layer name (default: ${suggestedFlowName})`}
          />
          <button onClick={handleCreate} disabled={createMutation.isPending} className="btn-primary px-4 py-2 text-xs">
            {createMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Create
          </button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          New logic layers are created as unassigned. Attach them from Workspace page. Trigger type is auto-detected from trigger nodes in Flow Builder.
        </p>
      </section>

      <section className="panel animate-rise p-4 md:p-5">
        <div className="grid gap-3 md:grid-cols-1">
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search logic layer or trigger..."
              className="input-base pl-10"
            />
          </label>
        </div>
      </section>

      <section className="space-y-3">
        {filteredFlows.map((flow: FlowSummary, index) => (
          <article
            key={flow.id}
            style={{ animationDelay: `${index * 35}ms` }}
            className="panel animate-rise flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between"
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-lg font-bold">{flow.name}</h3>
                <span className={flow.workspace_count > 0 ? "tag border-emerald-200 bg-emerald-50 text-emerald-700" : "tag border-amber-200 bg-amber-50 text-amber-700"}>
                  {flow.workspace_count > 0
                    ? `Used in ${flow.workspace_count} Workspace${flow.workspace_count > 1 ? "s" : ""}`
                    : "Unassigned"}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                Trigger: <span className="font-semibold text-foreground">{flow.trigger_type}</span>
              </p>
              {flow.description && <p className="line-clamp-2 text-sm text-muted-foreground">{flow.description}</p>}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete logic layer "${flow.name}" permanently?\n\nThis cannot be undone.`
                    )
                  ) {
                    deleteMutation.mutate(flow.id);
                  }
                }}
                disabled={deleteMutation.isPending && deletingFlowId === flow.id}
                className="btn-secondary px-3 py-2 text-xs text-destructive"
                title="Delete permanently"
                aria-label={`Delete logic layer ${flow.name} permanently`}
              >
                {deleteMutation.isPending && deletingFlowId === flow.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                Delete
              </button>
              <Link to={`/flows/${flow.id}`} className="btn-primary px-3 py-2 text-xs">
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Link>
            </div>
          </article>
        ))}

        {filteredFlows.length === 0 && (
          <section className="panel-muted flex min-h-[220px] items-center justify-center p-10 text-center">
            <div>
              <Workflow className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-semibold text-foreground">No logic layers found</p>
              <p className="text-sm text-muted-foreground">Try a different search keyword.</p>
            </div>
          </section>
        )}
      </section>
    </div>
  );
}
