import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExecutions } from "../lib/api";
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
} from "lucide-react";
import { cn } from "../lib/utils";
import ReactJson from "react-json-view";
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

export default function ExecutionLogs() {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["executions"],
    queryFn: () => getExecutions({ limit: 50 }),
    refetchInterval: 5000,
  });

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

  const executions = data?.executions || [];
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
          {isFetching ? "Refreshing" : "Auto refresh: 5s"}
        </div>
      </section>

      <section className="panel animate-rise overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 w-8" />
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
                        <td colSpan={6} className="px-4 py-4">
                          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                            <div className="panel overflow-auto p-3">
                              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Trigger Data</h4>
                              <ReactJson
                                src={exec.trigger_data}
                                name={false}
                                displayDataTypes={false}
                                enableClipboard={false}
                                collapsed={1}
                                style={{ fontSize: "12px", background: "transparent" }}
                              />
                            </div>

                            <div className="panel overflow-auto p-3">
                              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Execution Steps</h4>
                              <ReactJson
                                src={parseNodesExecuted(exec.nodes_executed)}
                                name={false}
                                displayDataTypes={false}
                                enableClipboard={false}
                                collapsed={1}
                                style={{ fontSize: "12px", background: "transparent" }}
                              />
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
                  <td colSpan={6} className="px-6 py-16 text-center text-muted-foreground">
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
