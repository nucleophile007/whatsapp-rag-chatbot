import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  clearMemoryForClient,
  deactivateMemoryLtmItem,
  getMemoryDebugSnapshot,
  getWorkspaces,
  upsertMemoryLtmItem,
} from "../lib/api";
import type { MemoryLtmItem, MemorySnapshotResponse } from "../lib/types";
import {
  BrainCircuit,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  Plus,
  Pencil,
  X,
  History,
  BookUser,
} from "lucide-react";

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

export default function MemoryDebug() {
  const [clientId, setClientId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [memoryScope, setMemoryScope] = useState<"client" | "client_workspace">("client");
  const [queryText, setQueryText] = useState("");
  const [historyLimit, setHistoryLimit] = useState("24");
  const [tokenBudget, setTokenBudget] = useState("1200");
  const [ltmLimit, setLtmLimit] = useState("50");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [snapshot, setSnapshot] = useState<MemorySnapshotResponse | null>(null);

  const [newKey, setNewKey] = useState("");
  const [newText, setNewText] = useState("");
  const [newCategory, setNewCategory] = useState("general");
  const [newConfidence, setNewConfidence] = useState("0.8");

  const [editKey, setEditKey] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [editCategory, setEditCategory] = useState("general");
  const [editConfidence, setEditConfidence] = useState("0.8");

  const workspacesQuery = useQuery({
    queryKey: ["workspaces", "memory-debug"],
    queryFn: getWorkspaces,
    staleTime: 30_000,
  });
  const workspaceOptions = workspacesQuery.data?.workspaces || [];

  const canLoad = useMemo(() => {
    const hasClient = clientId.trim().length > 0;
    if (!hasClient) return false;
    if (memoryScope === "client_workspace") {
      return workspaceId.trim().length > 0;
    }
    return true;
  }, [clientId, memoryScope, workspaceId]);

  const loadMutation = useMutation({
    mutationFn: getMemoryDebugSnapshot,
    onSuccess: (data) => {
      setSnapshot(data);
    },
  });

  const upsertMutation = useMutation({
    mutationFn: upsertMemoryLtmItem,
    onSuccess: () => {
      void handleLoadSnapshot();
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: deactivateMemoryLtmItem,
    onSuccess: () => {
      void handleLoadSnapshot();
    },
  });

  const clearMutation = useMutation({
    mutationFn: clearMemoryForClient,
    onSuccess: () => {
      setSnapshot(null);
    },
  });

  async function handleLoadSnapshot() {
    const trimmedClientId = clientId.trim();
    if (!trimmedClientId) return;
    await loadMutation.mutateAsync({
      clientId: trimmedClientId,
      query: queryText.trim(),
      historyLimit: Number.parseInt(historyLimit || "24", 10),
      tokenBudget: Number.parseInt(tokenBudget || "1200", 10),
      ltmLimit: Number.parseInt(ltmLimit || "50", 10),
      includeInactive,
      workspaceId: workspaceId.trim() || undefined,
      memoryScope,
    });
  }

  function beginEdit(item: MemoryLtmItem) {
    setEditKey(item.memory_key);
    setEditText(item.memory_text);
    setEditCategory(item.memory_category || "general");
    setEditConfidence(String(item.confidence ?? 0.8));
  }

  function resetEdit() {
    setEditKey(null);
    setEditText("");
    setEditCategory("general");
    setEditConfidence("0.8");
  }

  async function saveEdit() {
    const trimmedClientId = clientId.trim();
    const trimmedKey = (editKey || "").trim();
    if (!trimmedClientId || !trimmedKey || !editText.trim()) return;
    await upsertMutation.mutateAsync({
      clientId: trimmedClientId,
      workspaceId: workspaceId.trim() || undefined,
      memoryScope,
      data: {
        memory_key: trimmedKey,
        memory_text: editText.trim(),
        memory_category: editCategory.trim() || "general",
        confidence: Number.parseFloat(editConfidence || "0.8"),
      },
    });
    resetEdit();
  }

  async function addMemory() {
    const trimmedClientId = clientId.trim();
    if (!trimmedClientId || !newKey.trim() || !newText.trim()) return;
    await upsertMutation.mutateAsync({
      clientId: trimmedClientId,
      workspaceId: workspaceId.trim() || undefined,
      memoryScope,
      data: {
        memory_key: newKey.trim(),
        memory_text: newText.trim(),
        memory_category: newCategory.trim() || "general",
        confidence: Number.parseFloat(newConfidence || "0.8"),
        is_active: true,
      },
    });
    setNewKey("");
    setNewText("");
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
      <section className="panel animate-rise p-6">
        <div className="mb-4">
          <p className="tag bg-secondary text-secondary-foreground">
            <BrainCircuit className="h-3.5 w-3.5" />
            STM + LTM Inspector
          </p>
          <h1 className="title-xl mt-2">Memory Debug</h1>
          <p className="subtitle">Inspect per-user short-term context assembly and long-term memory records.</p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
          <input
            className="input-base md:col-span-2"
            placeholder="Client ID (example: 9198xxxx@s.whatsapp.net)"
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
          />
          <select
            className="input-base md:col-span-2"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.target.value)}
          >
            <option value="">Select Workspace {memoryScope === "client_workspace" ? "(Required)" : "(Optional)"}</option>
            {workspaceOptions.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name} ({workspace.id})
              </option>
            ))}
          </select>
          <select
            className="input-base md:col-span-2"
            value={memoryScope}
            onChange={(event) => setMemoryScope(event.target.value as "client" | "client_workspace")}
          >
            <option value="client">Scope: Client Only</option>
            <option value="client_workspace">Scope: Client + Workspace</option>
          </select>
          <input
            className="input-base md:col-span-2"
            placeholder="Query for semantic context build"
            value={queryText}
            onChange={(event) => setQueryText(event.target.value)}
          />
          <input className="input-base" value={historyLimit} onChange={(e) => setHistoryLimit(e.target.value)} placeholder="History limit" />
          <input className="input-base" value={tokenBudget} onChange={(e) => setTokenBudget(e.target.value)} placeholder="Token budget" />
          <input className="input-base" value={ltmLimit} onChange={(e) => setLtmLimit(e.target.value)} placeholder="LTM limit" />
          <label className="flex items-center gap-2 text-sm text-muted-foreground md:col-span-2">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            Include inactive memories
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-primary px-3 py-2 text-sm" onClick={() => void handleLoadSnapshot()} disabled={!canLoad || loadMutation.isPending}>
            {loadMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Load Snapshot
          </button>
          <button
            className="btn-secondary px-3 py-2 text-sm text-destructive"
            disabled={!canLoad || clearMutation.isPending}
            onClick={() => {
              if (!window.confirm("Clear conversation and deactivate all LTM for this client?")) return;
              clearMutation.mutate({
                clientId: clientId.trim(),
                workspaceId: workspaceId.trim() || undefined,
                memoryScope,
              });
            }}
          >
            {clearMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            Clear All Memory
          </button>
        </div>

        {(loadMutation.isError || upsertMutation.isError || deactivateMutation.isError || clearMutation.isError) && (
          <p className="mt-3 text-sm text-destructive">
            {String(
              (loadMutation.error as Error)?.message ||
                (upsertMutation.error as Error)?.message ||
                (deactivateMutation.error as Error)?.message ||
                (clearMutation.error as Error)?.message ||
                "Operation failed"
            )}
          </p>
        )}
        {workspacesQuery.isError && (
          <p className="mt-2 text-xs text-destructive">
            Failed to load workspaces for dropdown: {String((workspacesQuery.error as Error)?.message || "unknown error")}
          </p>
        )}
      </section>

      {snapshot && (
        <>
          <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="panel p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">History</p>
              <p className="mt-1 text-2xl font-bold">{snapshot.history_count}</p>
            </div>
            <div className="panel p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">LTM Items</p>
              <p className="mt-1 text-2xl font-bold">{snapshot.ltm_count}</p>
            </div>
            <div className="panel p-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Generated</p>
              <p className="mt-1 text-sm font-semibold">{formatTime(snapshot.generated_at)}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                scope: {snapshot.memory_scope || memoryScope}
                {snapshot.workspace_id ? ` • workspace: ${snapshot.workspace_id}` : ""}
              </p>
              {snapshot.effective_client_id ? (
                <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">
                  key: {snapshot.effective_client_id}
                </p>
              ) : null}
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="panel p-4">
              <h3 className="mb-2 text-sm font-semibold">Conversation Summary</h3>
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-xl border bg-secondary/20 p-3 text-xs">
                {snapshot.summary || "(empty)"}
              </pre>
            </div>
            <div className="panel p-4">
              <h3 className="mb-2 text-sm font-semibold">Context Preview (what model gets)</h3>
              <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-xl border bg-secondary/20 p-3 text-xs">
                {snapshot.context_preview || "(empty)"}
              </pre>
            </div>
          </section>

          <section className="panel p-4">
            <h3 className="mb-2 text-sm font-semibold">Conversation Slots</h3>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl border bg-secondary/20 p-3 text-xs">
              {JSON.stringify(snapshot.slots || {}, null, 2)}
            </pre>
          </section>

          <section className="panel p-4">
            <div className="mb-3 flex items-center gap-2">
              <BookUser className="h-4 w-4" />
              <h3 className="text-sm font-semibold">Long-Term Memory Items</h3>
            </div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-6">
              <input className="input-base md:col-span-2" placeholder="memory_key" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
              <input className="input-base md:col-span-2" placeholder="memory_text" value={newText} onChange={(e) => setNewText(e.target.value)} />
              <input className="input-base" placeholder="category" value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
              <input className="input-base" placeholder="confidence" value={newConfidence} onChange={(e) => setNewConfidence(e.target.value)} />
            </div>
            <button className="btn-secondary mt-2 px-3 py-2 text-xs" onClick={() => void addMemory()} disabled={upsertMutation.isPending}>
              {upsertMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Add / Upsert Memory
            </button>

            <div className="mt-4 space-y-2">
              {snapshot.ltm_items.map((item) => {
                const isEditing = editKey === item.memory_key;
                return (
                  <div key={item.memory_key} className="panel-muted rounded-xl p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <p className="font-mono text-xs">{item.memory_key}</p>
                      <div className="flex items-center gap-2">
                        <span className="tag">{item.memory_category}</span>
                        <span className="tag">conf {item.confidence.toFixed(2)}</span>
                        <span className="tag">hits {item.hit_count}</span>
                        <span className={`tag ${item.is_active ? "text-emerald-700" : "text-slate-500"}`}>
                          {item.is_active ? "active" : "inactive"}
                        </span>
                      </div>
                    </div>

                    {isEditing ? (
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-6">
                        <input className="input-base md:col-span-3" value={editText} onChange={(e) => setEditText(e.target.value)} />
                        <input className="input-base" value={editCategory} onChange={(e) => setEditCategory(e.target.value)} />
                        <input className="input-base" value={editConfidence} onChange={(e) => setEditConfidence(e.target.value)} />
                        <div className="flex gap-2">
                          <button className="btn-secondary px-2 py-2 text-xs" onClick={() => void saveEdit()} disabled={upsertMutation.isPending}>
                            <Save className="h-3.5 w-3.5" />
                          </button>
                          <button className="btn-secondary px-2 py-2 text-xs" onClick={resetEdit}>
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm">{item.memory_text}</p>
                        <p className="mt-1 text-xs text-muted-foreground">updated: {formatTime(item.updated_at)}</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button className="btn-secondary px-2 py-1 text-xs" onClick={() => beginEdit(item)}>
                            <Pencil className="h-3.5 w-3.5" />
                            Edit
                          </button>
                          <button
                            className="btn-secondary px-2 py-1 text-xs"
                            onClick={() =>
                              upsertMutation.mutate({
                                clientId: clientId.trim(),
                                workspaceId: workspaceId.trim() || undefined,
                                memoryScope,
                                data: {
                                  memory_key: item.memory_key,
                                  memory_text: item.memory_text,
                                  memory_category: item.memory_category,
                                  confidence: item.confidence,
                                  is_active: !item.is_active,
                                },
                              })
                            }
                            disabled={upsertMutation.isPending}
                          >
                            {item.is_active ? "Set Inactive" : "Reactivate"}
                          </button>
                          <button
                            className="btn-secondary px-2 py-1 text-xs text-destructive"
                            onClick={() =>
                              deactivateMutation.mutate({
                                clientId: clientId.trim(),
                                memoryKey: item.memory_key,
                                workspaceId: workspaceId.trim() || undefined,
                                memoryScope,
                              })
                            }
                            disabled={deactivateMutation.isPending}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Deactivate
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
              {snapshot.ltm_items.length === 0 && <p className="text-sm text-muted-foreground">No LTM items for this client.</p>}
            </div>
          </section>

          <section className="panel p-4">
            <div className="mb-3 flex items-center gap-2">
              <History className="h-4 w-4" />
              <h3 className="text-sm font-semibold">Recent Conversation History</h3>
            </div>
            <div className="space-y-2">
              {snapshot.history.map((item, idx) => (
                <div key={`${item.timestamp || "t"}-${idx}`} className="panel-muted rounded-xl p-3">
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>{item.role}</span>
                    <span>{formatTime(item.timestamp)}</span>
                  </div>
                  <p className="text-sm">{item.content}</p>
                </div>
              ))}
              {snapshot.history.length === 0 && <p className="text-sm text-muted-foreground">No conversation history.</p>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
