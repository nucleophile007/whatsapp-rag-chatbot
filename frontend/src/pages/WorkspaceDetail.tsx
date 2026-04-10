import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getWorkspace,
  updateWorkspace,
  deleteWorkspace,
  getCollections,
  getGroups,
  syncGroups,
  getContacts,
  syncContacts,
  getFlows,
  createFlow,
  attachFlowToWorkspace,
  detachFlowFromWorkspace,
  setWorkspaceStatus,
} from "../lib/api";
import {
  Loader2,
  Settings2,
  Target,
  CheckCircle2,
  Bot,
  MessageSquare,
  Filter,
  Users,
  Save,
  RefreshCw,
  Zap,
  Trash2,
  ArrowRight,
  ChevronLeft,
  Plus,
  AlertCircle,
  CircleDot,
  PauseCircle,
  PlayCircle,
  Search,
  X,
} from "lucide-react";
import { cn } from "../lib/utils";
import type { Collection, Contact, FlowCreateInput, FlowSummary, Group, WorkspaceFormInput } from "../lib/types";

export default function WorkspaceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [draftByWorkspaceId, setDraftByWorkspaceId] = useState<Record<string, Partial<WorkspaceFormInput>>>({});
  const [selectedExistingFlowId, setSelectedExistingFlowId] = useState("");
  const [manualContactInput, setManualContactInput] = useState("");
  const [contactSearchTerm, setContactSearchTerm] = useState("");
  const [showOnlyCompleteContacts, setShowOnlyCompleteContacts] = useState(false);

  const { data: workspace, isLoading: wsLoading, error: wsError } = useQuery({
    queryKey: ["workspace", id],
    queryFn: () => getWorkspace(id!),
    enabled: !!id,
  });

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
  });

  const { data: groupsData } = useQuery({
    queryKey: ["groups"],
    queryFn: getGroups,
  });

  const { data: contactsData } = useQuery({
    queryKey: ["contacts"],
    queryFn: getContacts,
  });

  const { data: flowsData, isLoading: flowsLoading } = useQuery({
    queryKey: ["flows", id],
    queryFn: () => getFlows(id),
    enabled: !!id,
  });

  const { data: allFlowsData } = useQuery({
    queryKey: ["flows", "all"],
    queryFn: () => getFlows(),
  });

  const updateMutation = useMutation({
    mutationFn: updateWorkspace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      if (id) {
        setDraftByWorkspaceId((prev) => ({ ...prev, [id]: {} }));
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWorkspace,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      navigate("/workspaces");
    },
  });

  const createFlowMutation = useMutation({
    mutationFn: createFlow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows", id] });
      queryClient.invalidateQueries({ queryKey: ["flows", "all"] });
    },
  });

  const detachFlowMutation = useMutation({
    mutationFn: (flowId: string) => detachFlowFromWorkspace({ workspaceId: id!, flowId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flows", id] });
      queryClient.invalidateQueries({ queryKey: ["flows", "all"] });
    },
  });

  const attachFlowMutation = useMutation({
    mutationFn: (flowId: string) => attachFlowToWorkspace({ workspaceId: id!, flowId }),
    onSuccess: () => {
      setSelectedExistingFlowId("");
      queryClient.invalidateQueries({ queryKey: ["flows", id] });
      queryClient.invalidateQueries({ queryKey: ["flows", "all"] });
    },
  });

  const syncGroupsMutation = useMutation({
    mutationFn: syncGroups,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["groups"] }),
  });

  const syncContactsMutation = useMutation({
    mutationFn: syncContacts,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["contacts"] }),
  });

  const statusMutation = useMutation({
    mutationFn: (nextState: boolean) => setWorkspaceStatus({ id: id!, is_active: nextState }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", id] });
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });

  const patchDraft = (patch: Partial<WorkspaceFormInput>) => {
    if (!id) return;
    setDraftByWorkspaceId((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] || {}),
        ...patch,
      },
    }));
  };

  if (wsLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  if (wsError || !workspace || !id) {
    return (
      <div className="mx-auto max-w-4xl p-8">
        <div className="panel border-destructive/25 bg-destructive/5 p-6 text-center">
          <AlertCircle className="mx-auto mb-3 h-10 w-10 text-destructive" />
          <h2 className="text-xl font-bold">Workspace not found</h2>
          <p className="subtitle mt-1">The workspace may have been deleted or is unavailable.</p>
          <button onClick={() => navigate("/workspaces")} className="btn-secondary mt-4">
            <ChevronLeft className="h-4 w-4" />
            Back to Workspaces
          </button>
        </div>
      </div>
    );
  }

  const baseFormData: WorkspaceFormInput = {
    name: workspace.name,
    knowledge_base_id: workspace.knowledge_base_id || "",
    system_prompt: workspace.system_prompt || "",
    user_prompt_template: workspace.user_prompt_template || "",
    low_quality_clarification_text: workspace.low_quality_clarification_text || "",
    contact_filter_mode: workspace.contact_filter_mode || "all",
    contact_chat_ids: workspace.contacts?.map((contact) => contact.chat_id) || [],
    group_ids: workspace.groups?.map((group) => group.id) || [],
  };

  const draft = draftByWorkspaceId[id] || {};
  const formData: WorkspaceFormInput = {
    name: draft.name ?? baseFormData.name,
    knowledge_base_id: draft.knowledge_base_id ?? baseFormData.knowledge_base_id,
    system_prompt: draft.system_prompt ?? baseFormData.system_prompt,
    user_prompt_template: draft.user_prompt_template ?? baseFormData.user_prompt_template,
    low_quality_clarification_text:
      draft.low_quality_clarification_text ?? baseFormData.low_quality_clarification_text,
    contact_filter_mode: draft.contact_filter_mode ?? baseFormData.contact_filter_mode,
    contact_chat_ids: draft.contact_chat_ids ?? baseFormData.contact_chat_ids,
    group_ids: draft.group_ids ?? baseFormData.group_ids,
  };

  const toggleGroupSelection = (groupId: string) => {
    const currentGroupIds = formData.group_ids;
    patchDraft({
      group_ids: currentGroupIds.includes(groupId)
        ? currentGroupIds.filter((gid) => gid !== groupId)
        : [...currentGroupIds, groupId],
    });
  };

  const toggleContactSelection = (chatId: string) => {
    const normalized = chatId.trim();
    if (!normalized) return;
    const current = formData.contact_chat_ids || [];
    patchDraft({
      contact_chat_ids: current.includes(normalized)
        ? current.filter((id) => id !== normalized)
        : [...current, normalized],
    });
  };

  const addManualContact = () => {
    const value = manualContactInput.trim();
    if (!value) return;
    const current = formData.contact_chat_ids || [];
    if (current.includes(value)) {
      setManualContactInput("");
      return;
    }
    patchDraft({ contact_chat_ids: [...current, value] });
    setManualContactInput("");
  };

  const removeManualContact = (chatId: string) => {
    const current = formData.contact_chat_ids || [];
    patchDraft({ contact_chat_ids: current.filter((id) => id !== chatId) });
  };

  const handleAddFlow = async () => {
    if (!id) return;
    const suggestedName = `Logic Layer ${flows.length + 1}`;
    const providedName = window.prompt("Enter logic layer name", suggestedName);
    if (providedName === null) return;
    const flowName = providedName.trim() || suggestedName;

    const payload: FlowCreateInput = {
      name: flowName,
      trigger_type: "whatsapp_mention",
      trigger_config: {},
      definition: {
        nodes: [{ id: "start", type: "trigger", data: { label: "Incoming Message", type: "trigger", config: {} }, position: { x: 0, y: 0 } }],
        edges: [],
      },
    };
    try {
      const created = await createFlowMutation.mutateAsync(payload);
      await attachFlowMutation.mutateAsync(created.flow_id);
    } catch (error) {
      console.error("Failed to create and attach logic layer", error);
    }
  };

  const collections = collectionsData?.collections || [];
  const groups = groupsData?.groups || [];
  const contacts = contactsData?.contacts || [];
  const flows = flowsData?.flows || [];
  const allFlows = allFlowsData?.flows || [];
  const attachableFlows = allFlows.filter((flow) => !id || !flow.workspace_ids.includes(id));
  const normalizedContactSearch = contactSearchTerm.trim().toLowerCase();
  const isCompleteContact = (contact: Contact): boolean => {
    const name = (contact.display_name || "").trim();
    const hasName = name.length > 0 && !/^\d+$/.test(name);
    const phoneJid = (contact.phone_jid || "").trim().toLowerCase();
    const wahaId = (contact.waha_contact_id || "").trim().toLowerCase();
    const hasPhone = phoneJid.endsWith("@s.whatsapp.net");
    const hasStableId = wahaId.endsWith("@c.us");
    return hasName && (hasPhone || hasStableId);
  };
  const filteredContacts = contacts.filter((contact: Contact) => {
    if (showOnlyCompleteContacts && !isCompleteContact(contact)) return false;
    if (!normalizedContactSearch) return true;
    const haystack = [
      contact.display_name,
      contact.phone_number,
      contact.chat_id,
      contact.lid,
      contact.phone_jid,
      contact.waha_contact_id,
      contact.id,
    ]
      .filter(Boolean)
      .map((value) => String(value).toLowerCase())
      .join(" ");
    return haystack.includes(normalizedContactSearch);
  });

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
      <section className="panel animate-rise p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <button onClick={() => navigate("/workspaces")} className="btn-secondary px-3 py-2 text-xs">
              <ChevronLeft className="h-3.5 w-3.5" />
              Back
            </button>

            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl font-bold">{workspace.name}</h1>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "tag",
                    workspace.is_active
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 bg-slate-50 text-slate-600"
                  )}
                >
                  <CircleDot className={cn("h-3.5 w-3.5", workspace.is_active && "animate-pulse")} />
                  {workspace.is_active ? "Active" : "Paused"}
                </span>
                <button
                  onClick={() => statusMutation.mutate(!workspace.is_active)}
                  disabled={statusMutation.isPending}
                  className="btn-secondary px-3 py-1.5 text-xs"
                >
                  {statusMutation.isPending ? (
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

            <p className="subtitle">Tune prompts, attach memory, assign groups, and build logic layers.</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                if (window.confirm("Delete this workspace? This cannot be undone.")) deleteMutation.mutate(id);
              }}
              className="btn-secondary text-destructive"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>

            <button
              onClick={() => updateMutation.mutate({ id, data: formData })}
              disabled={updateMutation.isPending || !formData.name.trim()}
              className="btn-primary"
            >
              {updateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <section className="xl:col-span-8 space-y-5">
          <article className="panel animate-rise p-5 md:p-6">
            <div className="mb-4 inline-flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-primary" />
              <h2 className="text-lg font-bold">Workspace Settings</h2>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Workspace Name</span>
                <input
                  value={formData.name}
                  onChange={(event) => patchDraft({ name: event.target.value })}
                  className="input-base"
                  placeholder="Sales Support Bot"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Knowledge Base</span>
                <select
                  value={formData.knowledge_base_id}
                  onChange={(event) => patchDraft({ knowledge_base_id: event.target.value })}
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
          </article>

          <article className="panel animate-rise p-5 md:p-6">
            <div className="mb-4 inline-flex items-center gap-2">
              <Bot className="h-4 w-4 text-primary" />
              <h2 className="text-lg font-bold">Prompt Strategy</h2>
            </div>

            <div className="space-y-4">
              <label className="space-y-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System Prompt</span>
                <textarea
                  rows={6}
                  value={formData.system_prompt ?? ""}
                  onChange={(event) => patchDraft({ system_prompt: event.target.value })}
                  className="input-base min-h-[145px] resize-y"
                  placeholder="High-level assistant behavior"
                />
              </label>

              <label className="space-y-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">User Prompt Template</span>
                <textarea
                  rows={4}
                  value={formData.user_prompt_template ?? ""}
                  onChange={(event) => patchDraft({ user_prompt_template: event.target.value })}
                  className="input-base min-h-[120px] resize-y"
                />
                <p className="text-xs text-muted-foreground">Variables: <code>{"{{body}}"}</code>, <code>{"{{rag_result}}"}</code></p>
              </label>

              <label className="space-y-1.5">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Low-Quality Clarification Text
                </span>
                <textarea
                  rows={3}
                  value={formData.low_quality_clarification_text ?? ""}
                  onChange={(event) => patchDraft({ low_quality_clarification_text: event.target.value })}
                  className="input-base min-h-[96px] resize-y"
                  placeholder="Message to send when query quality is too low (e.g., random/gibberish input)"
                />
                <p className="text-xs text-muted-foreground">
                  Used when message quality is too low to answer. Leave empty to use global default.
                </p>
              </label>
            </div>
          </article>

          <article className="panel animate-rise p-5 md:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <div className="inline-flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" />
                <h2 className="text-lg font-bold">Group Assignment</h2>
              </div>

              <button
                onClick={() => syncGroupsMutation.mutate()}
                disabled={syncGroupsMutation.isPending}
                className="btn-secondary px-3 py-2 text-xs"
              >
                {syncGroupsMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Sync Groups
              </button>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {groups.map((group: Group) => {
                const selected = formData.group_ids.includes(group.id);
                return (
                  <button
                    key={group.id}
                    onClick={() => toggleGroupSelection(group.id)}
                    className={cn(
                      "rounded-xl border p-3 text-left transition-colors",
                      selected ? "border-primary/40 bg-primary/5" : "bg-white hover:bg-secondary"
                    )}
                  >
                    <div className="inline-flex items-center gap-2 text-sm font-semibold">
                      {selected ? <CheckCircle2 className="h-4 w-4 text-primary" /> : <Target className="h-4 w-4 text-muted-foreground" />}
                      <span className="truncate">{group.name}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">{group.chat_id}</p>
                  </button>
                );
              })}
            </div>

            <div className="mt-6 border-t border-dashed pt-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="inline-flex items-center gap-2">
                  <Filter className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold">Individual Contact Filter</h3>
                </div>
                <button
                  onClick={() => syncContactsMutation.mutate()}
                  disabled={syncContactsMutation.isPending}
                  className="btn-secondary px-3 py-2 text-xs"
                >
                  {syncContactsMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                  Sync Contacts
                </button>
              </div>

              <p className="mb-3 text-xs text-muted-foreground">
                `Only` = run workspace only for selected persons. `Except` = run for everyone except selected persons.
              </p>

              <div className="mb-4 flex flex-wrap gap-2">
                {(["all", "only", "except"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => patchDraft({ contact_filter_mode: mode })}
                    className={cn(
                      "rounded-xl border px-3 py-2 text-xs font-semibold capitalize",
                      (formData.contact_filter_mode || "all") === mode
                        ? "border-primary/40 bg-primary/5 text-primary"
                        : "bg-white text-muted-foreground hover:bg-secondary"
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>

              <div className="mb-3 flex flex-wrap gap-2">
                <input
                  value={manualContactInput}
                  onChange={(event) => setManualContactInput(event.target.value)}
                  placeholder="Add phone or JID (e.g. 91810... or 91810...@s.whatsapp.net)"
                  className="input-base min-w-[280px] flex-1"
                />
                <button onClick={addManualContact} className="btn-secondary px-3 py-2 text-xs">
                  <Plus className="h-3.5 w-3.5" />
                  Add Contact
                </button>
              </div>

              <div className="mb-4 flex flex-wrap gap-2">
                <div className="relative min-w-[280px] flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    value={contactSearchTerm}
                    onChange={(event) => setContactSearchTerm(event.target.value)}
                    placeholder="Search by name, phone, lid, id, or chat id"
                    className="input-base pl-9"
                  />
                </div>
                {contactSearchTerm.trim() && (
                  <button onClick={() => setContactSearchTerm("")} className="btn-secondary px-3 py-2 text-xs">
                    Clear Search
                  </button>
                )}
              </div>

              <div className="mb-4 flex items-center gap-2">
                <input
                  id="only-complete-contacts"
                  type="checkbox"
                  checked={showOnlyCompleteContacts}
                  onChange={(event) => setShowOnlyCompleteContacts(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                />
                <label htmlFor="only-complete-contacts" className="text-xs text-muted-foreground">
                  Show only complete contacts (name + phone or @c.us id)
                </label>
              </div>

              {formData.contact_chat_ids && formData.contact_chat_ids.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {formData.contact_chat_ids.map((chatId) => (
                    <span key={chatId} className="tag border-slate-200 bg-slate-50 text-slate-700">
                      {chatId}
                      <button
                        onClick={() => removeManualContact(chatId)}
                        className="ml-1 rounded p-0.5 hover:bg-slate-200"
                        aria-label={`remove ${chatId}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {filteredContacts.map((contact: Contact) => {
                  const selected = (formData.contact_chat_ids || []).includes(contact.chat_id);
                  const primaryName =
                    contact.display_name ||
                    contact.phone_number ||
                    contact.phone_jid ||
                    contact.waha_contact_id ||
                    contact.lid ||
                    contact.chat_id;
                  return (
                    <button
                      key={contact.id}
                      onClick={() => toggleContactSelection(contact.chat_id)}
                      className={cn(
                        "rounded-xl border p-3 text-left transition-colors",
                        selected ? "border-primary/40 bg-primary/5" : "bg-white hover:bg-secondary"
                      )}
                    >
                      <div className="inline-flex items-center gap-2 text-sm font-semibold">
                        {selected ? (
                          <CheckCircle2 className="h-4 w-4 text-primary" />
                        ) : (
                          <Users className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="truncate">{primaryName}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">chat: {contact.chat_id}</p>
                      {contact.phone_jid && <p className="truncate text-[11px] text-muted-foreground">phone: {contact.phone_jid}</p>}
                      {contact.lid && <p className="truncate text-[11px] text-muted-foreground">lid: {contact.lid}</p>}
                      {contact.waha_contact_id && (
                        <p className="truncate text-[11px] text-muted-foreground">id: {contact.waha_contact_id}</p>
                      )}
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {contact.source} {contact.last_seen_at ? `• seen ${new Date(contact.last_seen_at).toLocaleString()}` : ""}
                      </p>
                    </button>
                  );
                })}
              </div>
              {contacts.length === 0 && (
                <p className="mt-3 text-xs text-muted-foreground">
                  No contacts synced yet. Click `Sync Contacts` or wait for incoming messages.
                </p>
              )}
              {contacts.length > 0 && filteredContacts.length === 0 && (
                <p className="mt-3 text-xs text-muted-foreground">
                  No contacts match your search.
                </p>
              )}
            </div>
          </article>
        </section>

        <aside className="xl:col-span-4 space-y-5">
          <article className="panel animate-rise p-5 md:p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="inline-flex items-center gap-2">
                <Zap className="h-4 w-4 text-primary" />
                <h3 className="text-lg font-bold">Logic Layers</h3>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button onClick={handleAddFlow} disabled={createFlowMutation.isPending} className="btn-secondary px-3 py-2 text-xs">
                  <Plus className="h-3.5 w-3.5" />
                  New
                </button>
              </div>
            </div>

            <div className="mb-3 space-y-2 rounded-xl border border-border/70 bg-secondary/20 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Attach Existing Logic Layer</p>
              <div className="flex gap-2">
                <select
                  value={selectedExistingFlowId}
                  onChange={(event) => setSelectedExistingFlowId(event.target.value)}
                  className="input-base"
                >
                  <option value="">Select existing layer...</option>
                  {attachableFlows.map((flow) => (
                    <option key={flow.id} value={flow.id}>
                      {flow.name}
                      {flow.workspace_count > 0 ? ` (used in ${flow.workspace_count} workspace${flow.workspace_count > 1 ? "s" : ""})` : " (unassigned)"}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => selectedExistingFlowId && attachFlowMutation.mutate(selectedExistingFlowId)}
                  disabled={!selectedExistingFlowId || attachFlowMutation.isPending}
                  className="btn-secondary px-3 py-2 text-xs disabled:opacity-50"
                >
                  {attachFlowMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Attach
                </button>
              </div>
            </div>

            <div className="space-y-2">
              {flows.map((flow: FlowSummary) => (
                <div key={flow.id} className="panel flex items-center justify-between px-3 py-3">
                  <div className="min-w-0">
                    <h4 className="truncate text-sm font-semibold">{flow.name}</h4>
                    <p className="text-xs text-muted-foreground">Trigger: {flow.trigger_type}</p>
                  </div>
                  <div className="ml-2 flex gap-1">
                    <button
                      onClick={() => {
                        if (
                          window.confirm(
                            "Detach this logic layer from this workspace? It will remain available in Logic Layers."
                          )
                        ) {
                          detachFlowMutation.mutate(flow.id);
                        }
                      }}
                      disabled={detachFlowMutation.isPending}
                      className="btn-secondary px-2 py-2"
                      aria-label={`Detach flow ${flow.name}`}
                      title="Detach from workspace"
                    >
                      {detachFlowMutation.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <span className="text-[10px] font-semibold">Detach</span>
                      )}
                    </button>
                    <button
                      onClick={() => navigate(`/flows/${flow.id}`)}
                      className="btn-secondary px-2 py-2 text-primary"
                      aria-label={`Open flow ${flow.name}`}
                      title="Open flow"
                    >
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}

              {flows.length === 0 && (
                <div className="panel-muted p-6 text-center text-sm text-muted-foreground">No flow layers yet.</div>
              )}

              {flowsLoading && (
                <div className="flex justify-center py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                </div>
              )}
            </div>
          </article>

          <article className="panel border-primary/20 bg-primary/5 p-5">
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">Pro Tip</h4>
            <p className="text-sm text-primary/80">
              Flow layers execute before the base RAG prompt. Use them for command routing, keyword logic, or API integrations.
            </p>
          </article>
        </aside>
      </div>
    </div>
  );
}
