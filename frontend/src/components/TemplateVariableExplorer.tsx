import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search, Copy, Braces } from "lucide-react";
import { getExecutions } from "../lib/api";

interface TemplateVariableExplorerProps {
  flowId?: string;
  targetField?: string | null;
  onInsertTemplate?: (template: string) => void;
  width?: number;
}

type FlatEntry = {
  path: string;
  value: string;
  type: string;
};

const FALLBACK_TRIGGER = {
  id: "demo_message_id",
  body: "Hello bot, share policy details",
  from: "123456789@c.us",
  chatId: "123456789@g.us",
  mentionedIds: ["35077249618150@lid"],
  _waha: {
    event: "message",
    session: "default",
    engine: "NOWEB",
    timestamp: Date.now(),
  },
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const flattenValue = (value: unknown, prefix = "", depth = 0, out: FlatEntry[] = []): FlatEntry[] => {
  if (depth > 7) {
    return out;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      out.push({ path: prefix, value: "[]", type: "array" });
      return out;
    }
    value.forEach((item, index) => {
      const childPath = prefix ? `${prefix}.${index}` : String(index);
      flattenValue(item, childPath, depth + 1, out);
    });
    return out;
  }

  if (isObject(value)) {
    const entries = Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
    if (entries.length === 0) {
      out.push({ path: prefix, value: "{}", type: "object" });
      return out;
    }
    entries.forEach(([key, child]) => {
      const childPath = prefix ? `${prefix}.${key}` : key;
      flattenValue(child, childPath, depth + 1, out);
    });
    return out;
  }

  const normalized =
    typeof value === "string" ? value : value === undefined ? "undefined" : value === null ? "null" : String(value);
  out.push({
    path: prefix,
    value: normalized,
    type: Array.isArray(value) ? "array" : typeof value,
  });
  return out;
};

export default function TemplateVariableExplorer({ flowId, targetField, onInsertTemplate, width }: TemplateVariableExplorerProps) {
  const [search, setSearch] = useState("");
  const [copiedPath, setCopiedPath] = useState("");

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["executions", "flow-template-vars", flowId],
    queryFn: () => getExecutions({ flow_id: flowId, limit: 25 }),
    enabled: Boolean(flowId),
    refetchInterval: 7000,
  });

  const latestTriggerData = useMemo(() => {
    const executions = data?.executions || [];
    const latest = executions.find((execution) => Object.keys(execution.trigger_data || {}).length > 0);
    return latest?.trigger_data ?? FALLBACK_TRIGGER;
  }, [data]);
  const hasLivePayload = useMemo(() => {
    const executions = data?.executions || [];
    return executions.some((execution) => Object.keys(execution.trigger_data || {}).length > 0);
  }, [data]);

  const rows = useMemo(() => flattenValue(latestTriggerData).filter((row) => row.path.length > 0), [latestTriggerData]);

  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) => row.path.toLowerCase().includes(query) || row.value.toLowerCase().includes(query));
  }, [rows, search]);

  const handleCopy = async (path: string) => {
    const template = `{{trigger.${path}}}`;
    try {
      await navigator.clipboard.writeText(template);
      setCopiedPath(path);
      window.setTimeout(() => setCopiedPath(""), 1200);
    } catch {
      setCopiedPath("");
    }
  };

  const handleInsert = (path: string) => {
    const template = `{{trigger.${path}}}`;
    if (onInsertTemplate) {
      onInsertTemplate(template);
      return;
    }
    void handleCopy(path);
  };

  return (
    <aside className="shrink-0 border-l border-border/70 bg-white/88 p-5 overflow-y-auto" style={width ? { width } : undefined}>
      <div className="mb-4 rounded-xl border bg-secondary/40 p-3">
        <div className="mb-1 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          <Braces className="h-3.5 w-3.5" />
          Template Variables
          {(isLoading || isFetching) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        </div>
        <p className="text-xs text-muted-foreground">
          Live from latest flow execution payload. Click row to copy template path.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Active field: <span className="font-semibold text-foreground">{targetField || "None selected"}</span>
        </p>
        {!hasLivePayload && <p className="mt-2 text-xs text-amber-700">No recent execution found, showing sample variables.</p>}
      </div>

      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search path or value..."
          className="input-base pl-9"
        />
      </div>

      <div className="space-y-2">
        {filteredRows.map((row) => (
          <div
            key={row.path}
            className="w-full rounded-lg border border-border/70 bg-white px-3 py-2 text-left hover:border-primary/40 hover:bg-primary/5"
          >
            <div className="flex items-start justify-between gap-2">
              <code className="truncate text-xs font-semibold text-foreground">{`{{trigger.${row.path}}}`}</code>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => handleCopy(row.path)}
                  className="inline-flex items-center gap-1 rounded-md border border-border/70 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground hover:bg-secondary/50"
                >
                  <Copy className="h-3 w-3" />
                  {copiedPath === row.path ? "Copied" : "Copy"}
                </button>
                <button
                  type="button"
                  onClick={() => handleInsert(row.path)}
                  className="inline-flex items-center gap-1 rounded-md border border-border/70 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground hover:bg-secondary/50"
                >
                  Insert
                </button>
              </div>
            </div>
            <p className="mt-1 truncate text-xs text-muted-foreground">{row.value || "(empty)"} <span className="ml-1 uppercase">[{row.type}]</span></p>
          </div>
        ))}

        {filteredRows.length === 0 && <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">No variables matched.</p>}
      </div>
    </aside>
  );
}
