import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getExecutions } from "../lib/api";
import { Loader2, Activity, CheckCircle2, AlertCircle, Clock, PlayCircle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "../lib/utils";
import ReactJson from "react-json-view";

export default function ExecutionLogs() {
    const [expandedRow, setExpandedRow] = useState<string | null>(null);

    // Fetch logs
    const { data, isLoading, error } = useQuery({
        queryKey: ['executions'],
        queryFn: () => getExecutions({ limit: 50 }),
        refetchInterval: 5000 // Auto-refresh logs every 5s
    });

    if (isLoading && !data) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-6 text-destructive">
                Error loading logs: {error.message}
            </div>
        );
    }

    const toggleRow = (id: string) => {
        setExpandedRow(expandedRow === id ? null : id);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Execution Logs</h1>
                    <p className="text-muted-foreground mt-1">
                        Monitor real-time AI activity
                    </p>
                </div>
            </div>

            <div className="rounded-md border bg-white shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="text-xs text-gray-700 uppercase bg-gray-50 border-b">
                            <tr>
                                <th className="px-6 py-3 w-10"></th>
                                <th className="px-6 py-3">Status</th>
                                <th className="px-6 py-3">Component</th>
                                <th className="px-6 py-3">User / Group</th>
                                <th className="px-6 py-3">Started At</th>
                                <th className="px-6 py-3">Activity</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data?.executions?.map((exec: any) => {
                                const componentName = exec.flow_id || "System";
                                const triggerSummary = exec.trigger_data?.from || "Unknown";
                                const stepCount = Array.isArray(exec.nodes_executed) ? exec.nodes_executed.length : 0;
                                const isExpanded = expandedRow === exec.id;

                                return (
                                    <React.Fragment key={exec.id}>
                                        <tr
                                            className={cn("bg-white border-b hover:bg-gray-50 cursor-pointer", isExpanded && "bg-gray-50")}
                                            onClick={() => toggleRow(exec.id)}
                                        >
                                            <td className="px-6 py-4">
                                                {isExpanded ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={cn(
                                                    "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium",
                                                    exec.status === "completed" ? "bg-green-100 text-green-800" :
                                                        exec.status === "failed" ? "bg-red-100 text-red-800" :
                                                            "bg-yellow-100 text-yellow-800"
                                                )}>
                                                    {exec.status === "completed" ? <CheckCircle2 className="h-3 w-3" /> :
                                                        exec.status === "failed" ? <AlertCircle className="h-3 w-3" /> :
                                                            <Clock className="h-3 w-3" />}
                                                    <span className="capitalize">{exec.status}</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-medium text-gray-900">
                                                <div className="flex items-center gap-2">
                                                    <Activity className="h-4 w-4 text-primary/50" />
                                                    <span className="truncate max-w-[150px]">{componentName}</span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-gray-500">
                                                {triggerSummary}
                                            </td>
                                            <td className="px-6 py-4 text-gray-500">
                                                {new Date(exec.started_at).toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-800 text-xs font-medium px-2.5 py-0.5 rounded border border-gray-200">
                                                    <PlayCircle className="h-3 w-3" /> {stepCount} Steps
                                                </span>
                                            </td>
                                        </tr>
                                        {isExpanded && (
                                            <tr className="bg-gray-50/50">
                                                <td colSpan={6} className="px-6 py-4">
                                                    <div className="grid grid-cols-2 gap-4">
                                                        <div className="bg-white rounded border p-4">
                                                            <h4 className="text-xs font-bold uppercase text-gray-500 mb-2">Trigger Data</h4>
                                                            <ReactJson
                                                                src={exec.trigger_data}
                                                                name={false}
                                                                displayDataTypes={false}
                                                                enableClipboard={false}
                                                                collapsed={1}
                                                                style={{ fontSize: '12px' }}
                                                            />
                                                        </div>
                                                        <div className="bg-white rounded border p-4">
                                                            <h4 className="text-xs font-bold uppercase text-gray-500 mb-2">Execution Steps</h4>
                                                            <ReactJson
                                                                src={typeof exec.nodes_executed === 'string' ? JSON.parse(exec.nodes_executed) : (exec.nodes_executed || [])}
                                                                name={false}
                                                                displayDataTypes={false}
                                                                enableClipboard={false}
                                                                collapsed={1}
                                                                style={{ fontSize: '12px' }}
                                                            />
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}

                            {data?.executions?.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-12 text-center text-muted-foreground">
                                        No execution logs found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
