import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clearExecutions, deleteExecutionsBulk, getExecutions } from "../lib/api";
import {
  Loader2,
  Activity,
  CheckCircle2,
  AlertCircle,
  Clock,
  PlayCircle,
  ChevronDown,
  ChevronRight,
  Radar,
  Trash2,
} from "lucide-react";
import { cn } from "../lib/utils";
import type { ExecutionRecord } from "../lib/types";

function parseNodesExecuted(nodes: ExecutionRecord["nodes_executed"]): unknown[] {
  if (!nodes) return [];
  if (Array.isArray(nodes)) return nodes;
  if (typeof nodes === "string") {
    try {
      const parsed = JSON.parse(nodes);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function renderPrettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

export default function ExecutionLogs() {
  const queryClient = useQueryClient();
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["executions"],
    queryFn: () => getExecutions({ limit: 30 }),
    refetchInterval: 10000,
    refetchOnWindowFocus: false,
  });

  const executions = data?.executions ?? [];
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const activeSelectedIds = useMemo(
    () => selectedIds.filter((id) => executions.some((execution) => execution.id === id)),
    [selectedIds, executions]
  );
  const isAllVisibleSelected =
    executions.length > 0 && executions.every((execution) => selectedIdSet.has(execution.id));

  const bulkDeleteMutation = useMutation({
    mutationFn: (executionIds: string[]) => deleteExecutionsBulk(executionIds),
    onSuccess: () => {
      setSelectedIds([]);
      setExpandedRow(null);
      queryClient.invalidateQueries({ queryKey: ["executions"] });
    },
  });

  const clearLogsMutation = useMutation({
    mutationFn: () => clearExecutions(),
    onSuccess: () => {
      setSelectedIds([]);
      setExpandedRow(null);
      queryClient.invalidateQueries({ queryKey: ["executions"] });
    },
  });

  const toggleSelectOne = (executionId: string) => {
    setSelectedIds((prev) =>
      prev.includes(executionId) ? prev.filter((id) => id !== executionId) : [...prev, executionId]
    );
  };

  const toggleSelectAllVisible = () => {
    if (isAllVisibleSelected) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(executions.map((execution) => execution.id));
  };

  const handleDeleteSelected = () => {
    if (activeSelectedIds.length === 0) return;
    const confirmed = window.confirm(
      `Delete ${activeSelectedIds.length} selected log${activeSelectedIds.length > 1 ? "s" : ""}?`
    );
    if (!confirmed) return;
    bulkDeleteMutation.mutate(activeSelectedIds);
  };

  const handleClearLogs = () => {
    if (executions.length === 0) return;
    const confirmed = window.confirm(
      "Clear all execution logs currently listed? This action cannot be undone."
    );
    if (!confirmed) return;
    clearLogsMutation.mutate();
  };

  if (isLoading && !data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-8">
        <div className="panel border-destructive/25 bg-destructive/5 p-4 text-destructive">
          Error loading logs: {(error as Error).message}
        </div>
      </div>
    );
  }

  const toggleRow = (id: string) => setExpandedRow((prev) => (prev === id ? null : id));

  return (
    <div className="mx-auto max-w-7xl space-y-7 p-5 md:p-8">
      <section className="panel animate-rise flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div className="page-header">
          <p className="tag bg-secondary text-secondary-foreground">
            <Radar className="h-3.5 w-3.5" />
            Runtime Visibility
          </p>
          <h1 className="title-xl">Execution Logs</h1>
          <p className="subtitle">Live stream of flow executions and payload traces.</p>
        </div>

        <div className="tag border-slate-200 bg-white text-slate-600">
          {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className="h-2 w-2 rounded-full bg-emerald-500" />}
          {isFetching ? "Refreshing" : "Auto refresh: 10s"}
        </div>
      </section>

      <section className="panel animate-rise overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 bg-secondary/20 px-4 py-3">
          <p className="text-xs text-muted-foreground">
            {activeSelectedIds.length > 0
              ? `${activeSelectedIds.length} selected`
              : `${executions.length} logs loaded`}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={activeSelectedIds.length === 0 || bulkDeleteMutation.isPending || clearLogsMutation.isPending}
              className="btn-secondary px-3 py-2 text-xs text-destructive disabled:opacity-50"
            >
              {bulkDeleteMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Delete Selected
            </button>
            <button
              type="button"
              onClick={handleClearLogs}
              disabled={executions.length === 0 || clearLogsMutation.isPending || bulkDeleteMutation.isPending}
              className="btn-secondary px-3 py-2 text-xs text-destructive disabled:opacity-50"
            >
              {clearLogsMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Clear Logs
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 w-8" />
                <th className="px-3 py-3 w-10">
                  <input
                    type="checkbox"
                    aria-label="Select all visible logs"
                    checked={isAllVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    className="h-4 w-4 rounded border-border"
                  />
                </th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Component</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3">Activity</th>
              </tr>
            </thead>

            <tbody>
              {executions.map((exec: ExecutionRecord) => {
                const componentName = exec.flow_id || "System";
                const triggerSummary = (exec.trigger_data?.from as string) || (exec.trigger_data?.chatId as string) || "Unknown";
                const stepCount = parseNodesExecuted(exec.nodes_executed).length;
                const isExpanded = expandedRow === exec.id;

                return (
                  <React.Fragment key={exec.id}>
                    <tr
                      className={cn(
                        "border-b border-border/60 transition-colors hover:bg-secondary/25",
                        isExpanded && "bg-secondary/30"
                      )}
                    >
                      <td className="px-4 py-3">
                        <button
                          onClick={() => toggleRow(exec.id)}
                          className="rounded-md p-1 text-muted-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                          aria-label={isExpanded ? "Collapse execution details" : "Expand execution details"}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                      </td>

                      <td className="px-3 py-3">
                        <input
                          type="checkbox"
                          aria-label={`Select execution ${exec.id}`}
                          checked={selectedIdSet.has(exec.id)}
                          onChange={() => toggleSelectOne(exec.id)}
                          className="h-4 w-4 rounded border-border"
                        />
                      </td>

                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "tag",
                            exec.status === "completed"
                              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                              : exec.status === "failed"
                                ? "border-rose-200 bg-rose-50 text-rose-700"
                                : "border-amber-200 bg-amber-50 text-amber-700"
                          )}
                        >
                          {exec.status === "completed" ? <CheckCircle2 className="h-3.5 w-3.5" /> : exec.status === "failed" ? <AlertCircle className="h-3.5 w-3.5" /> : <Clock className="h-3.5 w-3.5" />}
                          {exec.status}
                        </span>
                      </td>

                      <td className="px-4 py-3 font-semibold">
                        <div className="inline-flex items-center gap-2">
                          <Activity className="h-4 w-4 text-primary/70" />
                          <span className="max-w-[190px] truncate">{componentName}</span>
                        </div>
                      </td>

                      <td className="px-4 py-3 text-muted-foreground">{triggerSummary}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {exec.started_at ? new Date(exec.started_at).toLocaleString() : "-"}
                      </td>

                      <td className="px-4 py-3">
                        <span className="tag border-slate-200 bg-slate-50 text-slate-600">
                          <PlayCircle className="h-3.5 w-3.5" />
                          {stepCount} steps
                        </span>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="border-b border-border/60 bg-secondary/20">
                        <td colSpan={7} className="px-4 py-4">
                          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                            <div className="panel overflow-auto p-3">
                              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Trigger Data</h4>
                              <pre className="overflow-auto text-xs text-foreground">{renderPrettyJson(exec.trigger_data)}</pre>
                            </div>

                            <div className="panel overflow-auto p-3">
                              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Execution Steps</h4>
                              <pre className="overflow-auto text-xs text-foreground">
                                {renderPrettyJson(parseNodesExecuted(exec.nodes_executed))}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}

              {executions.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center text-muted-foreground">
                    No execution logs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
