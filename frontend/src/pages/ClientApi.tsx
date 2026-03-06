import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { BookOpen, Code2, Copy, KeyRound, Loader2, MessageSquare, Send, Shield } from "lucide-react";
import {
  clientChatRespond,
  clientChatRespondStream,
  createClientApiKey,
  deleteClientApiKey,
  getClientApiKeys,
  getClientChatDocsForCollection,
  getCollections,
  updateClientApiKey,
} from "../lib/api";

type TabKey = "interface" | "documentation" | "keys";
type PromptTechnique = "balanced" | "concise" | "detailed" | "strict_context" | "socratic";

type ChatLogItem = {
  role: "user" | "assistant";
  text: string;
  timestamp: string;
};

function buildDeviceFingerprint(): string {
  if (typeof window === "undefined") return "server-render";
  const parts = [
    navigator.userAgent || "ua",
    navigator.language || "lang",
    navigator.platform || "platform",
    `${window.screen?.width || 0}x${window.screen?.height || 0}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone || "tz",
  ];
  return parts.join("|");
}

function parseCollectionCsv(raw: string): string[] {
  const seen = new Set<string>();
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

export default function ClientApi() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<TabKey>("interface");
  const [message, setMessage] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [selectedCollectionName, setSelectedCollectionName] = useState("");
  const [clientSystem, setClientSystem] = useState(() => (typeof navigator !== "undefined" ? navigator.platform || "web" : "web"));
  const [manualClientId, setManualClientId] = useState("");
  const [conversationLimit, setConversationLimit] = useState(6);
  const [clearOnNextSend, setClearOnNextSend] = useState(false);
  const [resolvedClientId, setResolvedClientId] = useState("");
  const [chatLog, setChatLog] = useState<ChatLogItem[]>([]);
  const [errorText, setErrorText] = useState("");
  const [streamMode, setStreamMode] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [userPromptTemplate, setUserPromptTemplate] = useState("");
  const [promptTechnique, setPromptTechnique] = useState<PromptTechnique>("balanced");
  const [rateLimitHint, setRateLimitHint] = useState("");

  const [keyName, setKeyName] = useState("");
  const [keyDescription, setKeyDescription] = useState("");
  const [keyAllowAllCollections, setKeyAllowAllCollections] = useState(false);
  const [keyAllowedCollectionsRaw, setKeyAllowedCollectionsRaw] = useState("");
  const [keyDefaultCollection, setKeyDefaultCollection] = useState("");
  const [keyDailyLimitPerDevice, setKeyDailyLimitPerDevice] = useState(0);
  const [keyDefaultSystemPrompt, setKeyDefaultSystemPrompt] = useState("");
  const [keyDefaultUserPromptTemplate, setKeyDefaultUserPromptTemplate] = useState("");
  const [keyDefaultPromptTechnique, setKeyDefaultPromptTechnique] = useState<PromptTechnique>("balanced");
  const [keyActive, setKeyActive] = useState(true);
  const [generatedApiKey, setGeneratedApiKey] = useState("");
  const [keyErrorText, setKeyErrorText] = useState("");

  const collectionsQuery = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
  });

  const docsQuery = useQuery({
    queryKey: ["client-chat-docs", apiKey, selectedCollectionName],
    queryFn: () => getClientChatDocsForCollection(selectedCollectionName || undefined, apiKey),
  });

  const keysQuery = useQuery({
    queryKey: ["client-chat-keys", adminKey, apiKey],
    queryFn: () => getClientApiKeys(adminKey || undefined, apiKey || undefined),
    enabled: activeTab === "keys",
  });

  const buildChatPayload = (queryText: string) => ({
    message: queryText,
    client_id: manualClientId.trim() || undefined,
    collection_name: selectedCollectionName.trim() || undefined,
    client_system: clientSystem.trim() || "web",
    device_fingerprint: buildDeviceFingerprint(),
    conversation_limit: conversationLimit,
    clear_history: clearOnNextSend,
    system_prompt: systemPrompt.trim() || undefined,
    user_prompt_template: userPromptTemplate.trim() || undefined,
    prompt_technique: promptTechnique,
  });

  const chatMutation = useMutation({
    mutationFn: (queryText: string) => clientChatRespond(buildChatPayload(queryText), apiKey),
    onMutate: (queryText) => {
      setErrorText("");
      setChatLog((prev) => [...prev, { role: "user", text: queryText, timestamp: new Date().toISOString() }]);
    },
    onSuccess: (data) => {
      setResolvedClientId(data.client_id);
      setRateLimitHint(
        data.rate_limit.enabled
          ? `Rate: ${data.rate_limit.used}/${data.rate_limit.limit} today (remaining ${data.rate_limit.remaining ?? "-"})`
          : "Rate limit disabled"
      );
      setChatLog((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.response_mode === "rag" && data.collection_name ? `[${data.collection_name}] ${data.reply}` : data.reply,
          timestamp: data.timestamp,
        },
      ]);
      setClearOnNextSend(false);
    },
    onError: (error) => {
      let detail = "Chat request failed.";
      if (axios.isAxiosError(error)) {
        const body = error.response?.data as { detail?: unknown } | undefined;
        if (typeof body?.detail === "string") detail = body.detail;
      } else if (error instanceof Error && error.message) {
        detail = error.message;
      }
      setErrorText(detail);
      setChatLog((prev) => [...prev, { role: "assistant", text: `Error: ${detail}`, timestamp: new Date().toISOString() }]);
    },
  });

  const createKeyMutation = useMutation({
    mutationFn: () =>
      createClientApiKey(
        {
          name: keyName,
          description: keyDescription || undefined,
          allow_all_collections: keyAllowAllCollections,
          allowed_collections: parseCollectionCsv(keyAllowedCollectionsRaw),
          default_collection_name: keyDefaultCollection.trim() || undefined,
          daily_limit_per_device: keyDailyLimitPerDevice,
          default_system_prompt: keyDefaultSystemPrompt.trim() || undefined,
          default_user_prompt_template: keyDefaultUserPromptTemplate.trim() || undefined,
          default_prompt_technique: keyDefaultPromptTechnique,
          is_active: keyActive,
        },
        adminKey || undefined,
        apiKey || undefined
      ),
    onSuccess: (data) => {
      setGeneratedApiKey(data.api_key || "");
      setKeyErrorText("");
      setKeyName("");
      setKeyDescription("");
      setKeyAllowAllCollections(false);
      setKeyAllowedCollectionsRaw("");
      setKeyDefaultCollection("");
      setKeyDailyLimitPerDevice(0);
      setKeyDefaultSystemPrompt("");
      setKeyDefaultUserPromptTemplate("");
      setKeyDefaultPromptTechnique("balanced");
      setKeyActive(true);
      queryClient.invalidateQueries({ queryKey: ["client-chat-keys"] });
    },
    onError: (error) => {
      let detail = "Key creation failed.";
      if (axios.isAxiosError(error)) {
        const body = error.response?.data as { detail?: unknown } | undefined;
        if (typeof body?.detail === "string") detail = body.detail;
      }
      setKeyErrorText(detail);
    },
  });

  const updateKeyMutation = useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: Record<string, unknown> }) =>
      updateClientApiKey(keyId, payload, adminKey || undefined, apiKey || undefined),
    onSuccess: (data) => {
      if (data.api_key) setGeneratedApiKey(data.api_key);
      queryClient.invalidateQueries({ queryKey: ["client-chat-keys"] });
    },
    onError: (error) => {
      let detail = "Key update failed.";
      if (axios.isAxiosError(error)) {
        const body = error.response?.data as { detail?: unknown } | undefined;
        if (typeof body?.detail === "string") detail = body.detail;
      }
      setKeyErrorText(detail);
    },
  });

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: string) => deleteClientApiKey(keyId, adminKey || undefined, apiKey || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["client-chat-keys"] });
    },
    onError: (error) => {
      let detail = "Key delete failed.";
      if (axios.isAxiosError(error)) {
        const body = error.response?.data as { detail?: unknown } | undefined;
        if (typeof body?.detail === "string") detail = body.detail;
      }
      setKeyErrorText(detail);
    },
  });

  const endpoint = docsQuery.data?.base_url && docsQuery.data?.endpoint
    ? `${docsQuery.data.base_url}${docsQuery.data.endpoint}`
    : `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/chat/respond`;
  const streamEndpoint = docsQuery.data?.base_url && docsQuery.data?.stream_endpoint
    ? `${docsQuery.data.base_url}${docsQuery.data.stream_endpoint}`
    : `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/chat/respond/stream`;

  const canSend = message.trim().length > 0 && !chatMutation.isPending && !isStreaming;
  const helperText = useMemo(() => {
    if (resolvedClientId) return `Resolved client_id: ${resolvedClientId}`;
    return "If no manual client_id is provided, backend derives it from IP + system + browser signal.";
  }, [resolvedClientId]);

  const scopedCollections = docsQuery.data?.available_collections || [];
  const allCollections = collectionsQuery.data?.collections || [];
  const availableCollections = scopedCollections.length > 0 || docsQuery.data?.auth.required
    ? scopedCollections
    : allCollections.map((collection) => collection.name);

  const selectedModeText = selectedCollectionName
    ? `RAG mode on knowledge space: ${selectedCollectionName}`
    : "Direct model mode (no KB selected)";

  const sendMessage = async () => {
    const payload = message.trim();
    if (!payload) return;
    setMessage("");

    if (!streamMode) {
      chatMutation.mutate(payload);
      return;
    }

    setErrorText("");
    setIsStreaming(true);
    setChatLog((prev) => [
      ...prev,
      { role: "user", text: payload, timestamp: new Date().toISOString() },
      { role: "assistant", text: "", timestamp: new Date().toISOString() },
    ]);

    try {
      await clientChatRespondStream(
        buildChatPayload(payload),
        (event) => {
          if (event.type === "token") {
            setChatLog((prev) => {
              if (prev.length === 0) return prev;
              const idx = prev.length - 1;
              const last = prev[idx];
              if (last.role !== "assistant") return prev;
              const next = [...prev];
              next[idx] = { ...last, text: `${last.text}${event.data.text}` };
              return next;
            });
          }

          if (event.type === "done") {
            setResolvedClientId(event.data.client_id);
            setRateLimitHint(
              event.data.rate_limit.enabled
                ? `Rate: ${event.data.rate_limit.used}/${event.data.rate_limit.limit} today (remaining ${event.data.rate_limit.remaining ?? "-"})`
                : "Rate limit disabled"
            );
            setChatLog((prev) => {
              if (prev.length === 0) return prev;
              const idx = prev.length - 1;
              const last = prev[idx];
              if (last.role !== "assistant") return prev;
              const next = [...prev];
              next[idx] = {
                ...last,
                text:
                  event.data.response_mode === "rag" && event.data.collection_name
                    ? `[${event.data.collection_name}] ${event.data.reply}`
                    : event.data.reply,
                timestamp: event.data.timestamp,
              };
              return next;
            });
            setClearOnNextSend(false);
          }

          if (event.type === "error") {
            setErrorText(event.data.detail || "Stream error");
            setChatLog((prev) => [
              ...prev,
              { role: "assistant", text: `Error: ${event.data.detail || "Stream error"}`, timestamp: new Date().toISOString() },
            ]);
          }
        },
        apiKey
      );
    } catch (error) {
      let detail = "Stream request failed.";
      if (axios.isAxiosError(error)) {
        const body = error.response?.data as { detail?: unknown } | undefined;
        if (typeof body?.detail === "string") detail = body.detail;
      } else if (error instanceof Error && error.message) {
        detail = error.message;
      }
      setErrorText(detail);
      setChatLog((prev) => [...prev, { role: "assistant", text: `Error: ${detail}`, timestamp: new Date().toISOString() }]);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
      <section className="panel animate-rise flex flex-col gap-3 p-6 md:flex-row md:items-center md:justify-between">
        <div className="page-header">
          <p className="tag bg-secondary text-secondary-foreground">
            <Code2 className="h-3.5 w-3.5" />
            Public Integration API
          </p>
          <h1 className="title-xl">Client Chat API</h1>
          <p className="subtitle">Dynamic prompt controls, per-device/day limits, and SSE streaming for client websites.</p>
        </div>
        <div className="panel-muted flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
          <MessageSquare className="h-4 w-4 text-primary" />
          Endpoint: <span className="font-semibold text-foreground">{streamMode ? streamEndpoint : endpoint}</span>
        </div>
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap gap-2">
          <button className={`btn-secondary ${activeTab === "interface" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setActiveTab("interface")}>
            <MessageSquare className="h-4 w-4" />
            Interface
          </button>
          <button className={`btn-secondary ${activeTab === "documentation" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setActiveTab("documentation")}>
            <BookOpen className="h-4 w-4" />
            Documentation
          </button>
          <button className={`btn-secondary ${activeTab === "keys" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setActiveTab("keys")}>
            <Shield className="h-4 w-4" />
            Key Management
          </button>
        </div>
      </section>

      {activeTab === "interface" ? (
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <aside className="panel space-y-4 p-5 lg:col-span-4">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Client Controls</h2>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Manual client_id (optional)
              <input value={manualClientId} onChange={(event) => setManualClientId(event.target.value)} className="input-base mt-1" placeholder="Leave empty to auto-derive" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Client System
              <input value={clientSystem} onChange={(event) => setClientSystem(event.target.value)} className="input-base mt-1" placeholder="web / ios / android" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Knowledge Space
              <select value={selectedCollectionName} onChange={(event) => setSelectedCollectionName(event.target.value)} className="input-base mt-1">
                <option value="">Direct model (no KB)</option>
                {availableCollections.map((collectionName) => (
                  <option key={collectionName} value={collectionName}>{collectionName}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              API Key (client key)
              <div className="relative mt-1">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="input-base pl-9" placeholder="X-Client-Api-Key" />
              </div>
            </label>
            <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <input type="checkbox" checked={streamMode} onChange={(event) => setStreamMode(event.target.checked)} className="h-4 w-4" />
              Stream via SSE
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Prompt Technique
              <select value={promptTechnique} onChange={(event) => setPromptTechnique(event.target.value as PromptTechnique)} className="input-base mt-1">
                {(docsQuery.data?.supported_prompt_techniques || ["balanced", "concise", "detailed", "strict_context", "socratic"]).map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              System Prompt (optional)
              <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} className="input-base mt-1 min-h-[96px]" placeholder="Custom assistant behavior..." />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              User Prompt Template (optional)
              <textarea value={userPromptTemplate} onChange={(event) => setUserPromptTemplate(event.target.value)} className="input-base mt-1 min-h-[96px]" placeholder="e.g. Summarize: {{query}}" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Conversation window
              <input type="number" min={1} max={20} value={conversationLimit} onChange={(event) => setConversationLimit(Math.max(1, Math.min(20, Number(event.target.value || 6))))} className="input-base mt-1" />
            </label>
            <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <input type="checkbox" checked={clearOnNextSend} onChange={(event) => setClearOnNextSend(event.target.checked)} className="h-4 w-4" />
              Clear history on next send
            </label>
            <p className="text-xs text-muted-foreground">{helperText}</p>
            <p className="text-xs text-muted-foreground">{selectedModeText}</p>
            {rateLimitHint && <p className="text-xs font-semibold text-muted-foreground">{rateLimitHint}</p>}
          </aside>

          <div className="panel flex min-h-[560px] flex-col p-5 lg:col-span-8">
            <div className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-border/70 bg-secondary/25 p-4">
              {chatLog.length === 0 ? (
                <p className="text-sm text-muted-foreground">Send a message to test endpoint behavior.</p>
              ) : (
                chatLog.map((entry, index) => (
                  <div key={`${entry.timestamp}-${index}`} className={`rounded-xl px-3 py-2 text-sm ${entry.role === "user" ? "bg-primary/10" : "bg-white"}`}>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{entry.role}</p>
                    <p className="whitespace-pre-wrap">{entry.text || (isStreaming && entry.role === "assistant" ? "..." : "")}</p>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <input
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                className="input-base flex-1"
                placeholder="Type a message..."
                onKeyDown={(event) => {
                  if (event.key === "Enter" && canSend) {
                    void sendMessage();
                  }
                }}
              />
              <button className="btn-primary" disabled={!canSend} onClick={() => void sendMessage()}>
                {chatMutation.isPending || isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {streamMode ? "Stream" : "Send"}
              </button>
            </div>

            {errorText && <p className="mt-3 text-sm font-semibold text-destructive">{errorText}</p>}
          </div>
        </section>
      ) : activeTab === "documentation" ? (
        <section className="panel space-y-6 p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Integration Documentation</h2>
            <div className="text-xs text-muted-foreground">{docsQuery.isFetching ? "Refreshing docs..." : "Use these snippets in client apps"}</div>
          </div>

          {docsQuery.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading docs...
            </div>
          ) : docsQuery.isError ? (
            <p className="text-sm text-destructive">Failed to load API docs endpoint.</p>
          ) : (
            <div className="space-y-5">
              <div className="rounded-xl border border-border/70 bg-secondary/20 p-4 text-xs text-muted-foreground">
                <p>Auth mode: <span className="font-semibold text-foreground">{docsQuery.data?.auth.mode}</span></p>
                <p>Scope key: <span className="font-semibold text-foreground">{docsQuery.data?.scope.key_name || "global/open"}</span></p>
                <p>Default collection: <span className="font-semibold text-foreground">{docsQuery.data?.scope.default_collection_name || "none"}</span></p>
                <p>Daily per-device limit: <span className="font-semibold text-foreground">{docsQuery.data?.scope.daily_limit_per_device ?? "disabled"}</span></p>
                <p>Default prompt technique: <span className="font-semibold text-foreground">{docsQuery.data?.scope.default_prompt_technique}</span></p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">cURL Example</p>
                <pre className="mt-2 overflow-x-auto rounded-xl border border-border/70 bg-secondary/30 p-4 text-xs"><code>{docsQuery.data?.curl_example}</code></pre>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">JavaScript Example</p>
                <pre className="mt-2 overflow-x-auto rounded-xl border border-border/70 bg-secondary/30 p-4 text-xs"><code>{docsQuery.data?.javascript_example}</code></pre>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">SSE Streaming Example</p>
                <pre className="mt-2 overflow-x-auto rounded-xl border border-border/70 bg-secondary/30 p-4 text-xs"><code>{docsQuery.data?.sse_javascript_example}</code></pre>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Quick HTML Widget Template</p>
                <pre className="mt-2 overflow-x-auto rounded-xl border border-border/70 bg-secondary/30 p-4 text-xs"><code>{docsQuery.data?.html_widget_template}</code></pre>
              </div>
              <p className="text-xs text-muted-foreground">Active knowledge space in docs: {docsQuery.data?.active_collection_name || "None (direct mode)"}</p>
              <button className="btn-secondary" onClick={async () => {
                if (!docsQuery.data?.html_widget_template) return;
                await navigator.clipboard.writeText(docsQuery.data.html_widget_template);
              }}>
                <Copy className="h-4 w-4" />
                Copy Widget Template
              </button>
            </div>
          )}
        </section>
      ) : (
        <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <aside className="panel space-y-4 p-5 lg:col-span-4">
            <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Admin Auth</h2>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Admin Key (X-Client-Admin-Key)
              <input value={adminKey} onChange={(event) => setAdminKey(event.target.value)} className="input-base mt-1" placeholder="Required if CLIENT_CHAT_ADMIN_KEY is set" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Global API Key fallback (optional)
              <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="input-base mt-1" placeholder="X-Client-Api-Key" />
            </label>

            <h3 className="pt-2 text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">Create Key</h3>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Name
              <input value={keyName} onChange={(event) => setKeyName(event.target.value)} className="input-base mt-1" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Description
              <textarea value={keyDescription} onChange={(event) => setKeyDescription(event.target.value)} className="input-base mt-1 min-h-[72px]" />
            </label>
            <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <input type="checkbox" checked={keyAllowAllCollections} onChange={(event) => setKeyAllowAllCollections(event.target.checked)} className="h-4 w-4" />
              Allow all collections
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Allowed collections (comma separated)
              <input value={keyAllowedCollectionsRaw} onChange={(event) => setKeyAllowedCollectionsRaw(event.target.value)} className="input-base mt-1" placeholder="siteindex, docs, support" disabled={keyAllowAllCollections} />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Default collection (optional)
              <input value={keyDefaultCollection} onChange={(event) => setKeyDefaultCollection(event.target.value)} className="input-base mt-1" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Daily limit per IP+system (0 = disabled)
              <input type="number" min={0} value={keyDailyLimitPerDevice} onChange={(event) => setKeyDailyLimitPerDevice(Math.max(0, Number(event.target.value || 0)))} className="input-base mt-1" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Default prompt technique
              <select value={keyDefaultPromptTechnique} onChange={(event) => setKeyDefaultPromptTechnique(event.target.value as PromptTechnique)} className="input-base mt-1">
                <option value="balanced">balanced</option>
                <option value="concise">concise</option>
                <option value="detailed">detailed</option>
                <option value="strict_context">strict_context</option>
                <option value="socratic">socratic</option>
              </select>
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Default system prompt
              <textarea value={keyDefaultSystemPrompt} onChange={(event) => setKeyDefaultSystemPrompt(event.target.value)} className="input-base mt-1 min-h-[82px]" />
            </label>
            <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Default user prompt template
              <textarea value={keyDefaultUserPromptTemplate} onChange={(event) => setKeyDefaultUserPromptTemplate(event.target.value)} className="input-base mt-1 min-h-[82px]" />
            </label>
            <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <input type="checkbox" checked={keyActive} onChange={(event) => setKeyActive(event.target.checked)} className="h-4 w-4" />
              Key active
            </label>
            <button className="btn-primary w-full" disabled={createKeyMutation.isPending || !keyName.trim()} onClick={() => createKeyMutation.mutate()}>
              {createKeyMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4" />}
              Create key
            </button>

            {generatedApiKey && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs">
                <p className="font-semibold text-emerald-700">Generated API key (shown once)</p>
                <code className="mt-1 block break-all text-emerald-900">{generatedApiKey}</code>
                <button className="btn-secondary mt-2" onClick={async () => navigator.clipboard.writeText(generatedApiKey)}>
                  <Copy className="h-4 w-4" />
                  Copy key
                </button>
              </div>
            )}
            {keyErrorText && <p className="text-sm font-semibold text-destructive">{keyErrorText}</p>}
          </aside>

          <div className="panel p-5 lg:col-span-8">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold">Existing Keys</h2>
              <button className="btn-secondary" onClick={() => keysQuery.refetch()}>Refresh</button>
            </div>

            {keysQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading keys...
              </div>
            ) : keysQuery.isError ? (
              <p className="text-sm text-destructive">Unable to load keys. Check admin/global key headers.</p>
            ) : (keysQuery.data?.keys.length || 0) === 0 ? (
              <p className="text-sm text-muted-foreground">No keys found.</p>
            ) : (
              <div className="space-y-3">
                {keysQuery.data?.keys.map((key) => (
                  <div key={key.id} className="rounded-xl border border-border/70 bg-secondary/20 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">{key.name}</p>
                        <p className="text-xs text-muted-foreground">{key.description || "No description"}</p>
                        <p className="mt-1 text-xs text-muted-foreground">Prefix: {key.key_prefix}</p>
                        <p className="text-xs text-muted-foreground">Scope: {key.allow_all_collections ? "all collections" : key.allowed_collections.join(", ") || "none"}</p>
                        <p className="text-xs text-muted-foreground">Default collection: {key.default_collection_name || "none"}</p>
                        <p className="text-xs text-muted-foreground">Daily limit: {key.daily_limit_per_device ?? "disabled"}</p>
                        <p className="text-xs text-muted-foreground">Technique: {key.default_prompt_technique}</p>
                        <p className="text-xs text-muted-foreground">Status: {key.is_active ? "active" : "inactive"}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button className="btn-secondary" disabled={updateKeyMutation.isPending} onClick={() => updateKeyMutation.mutate({ keyId: key.id, payload: { is_active: !key.is_active } })}>
                          {key.is_active ? "Deactivate" : "Activate"}
                        </button>
                        <button className="btn-secondary" disabled={updateKeyMutation.isPending} onClick={() => updateKeyMutation.mutate({ keyId: key.id, payload: { rotate_key: true } })}>
                          Rotate
                        </button>
                        <button className="btn-secondary text-destructive" disabled={deleteKeyMutation.isPending} onClick={() => deleteKeyMutation.mutate(key.id)}>
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
