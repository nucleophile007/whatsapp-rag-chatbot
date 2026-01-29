import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
    getWorkspace,
    updateWorkspace,
    deleteWorkspace,
    getCollections,
    getGroups,
    syncGroups,
    getFlows,
    createFlow,
    deleteFlow,
    toggleWorkspace
} from "../lib/api";
import {
    Loader2,
    Settings2,
    Target,
    CheckCircle2,
    Bot,
    MessageSquare,
    Save,
    RefreshCw,
    Zap,
    Trash2,
    ArrowRight,
    ChevronLeft,
    Plus,
    AlertCircle
} from "lucide-react";
import { cn } from "../lib/utils";

export default function WorkspaceDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();

    // Form State
    const [formData, setFormData] = useState({
        name: "",
        knowledge_base_id: "",
        system_prompt: "",
        user_prompt_template: "",
        group_ids: [] as string[]
    });

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

    const { data: flowsData, isLoading: flowsLoading } = useQuery({
        queryKey: ["flows", id],
        queryFn: () => getFlows(id),
        enabled: !!id,
    });

    useEffect(() => {
        if (workspace) {
            setFormData({
                name: workspace.name,
                knowledge_base_id: workspace.knowledge_base_id || "",
                system_prompt: workspace.system_prompt || "",
                user_prompt_template: workspace.user_prompt_template || "",
                group_ids: workspace.groups?.map((g: any) => g.id) || []
            });
        }
    }, [workspace]);

    const updateMutation = useMutation({
        mutationFn: updateWorkspace,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workspace", id] });
            queryClient.invalidateQueries({ queryKey: ["workspaces"] });
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
        },
    });

    const deleteFlowMutation = useMutation({
        mutationFn: deleteFlow,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["flows", id] });
        },
    });

    const syncGroupsMutation = useMutation({
        mutationFn: syncGroups,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["groups"] });
        },
    });

    const toggleMutation = useMutation({
        mutationFn: () => toggleWorkspace(id!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workspace", id] });
            queryClient.invalidateQueries({ queryKey: ["workspaces"] });
        },
    });

    const toggleGroupSelection = (groupId: string) => {
        setFormData(prev => ({
            ...prev,
            group_ids: prev.group_ids.includes(groupId)
                ? prev.group_ids.filter(id => id !== groupId)
                : [...prev.group_ids, groupId]
        }));
    };

    const handleAddFlow = () => {
        if (!id) return;
        createFlowMutation.mutate({
            name: "New Automation Layer",
            workspace_id: id,
            trigger_type: "whatsapp_mention",
            trigger_config: {},
            definition: {
                nodes: [
                    { id: "start", type: "trigger", data: { label: "Incoming Message" }, position: { x: 0, y: 0 } }
                ],
                edges: []
            }
        });
    };

    if (wsLoading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-primary" /></div>;
    }

    if (wsError || !workspace) {
        return (
            <div className="p-8 max-w-7xl mx-auto text-center py-20">
                <AlertCircle className="h-16 w-16 text-red-400 mx-auto mb-4" />
                <h2 className="text-2xl font-bold">Workspace Not Found</h2>
                <p className="text-muted-foreground mt-2">The workspace you're looking for doesn't exist or has been deleted.</p>
                <button
                    onClick={() => navigate("/workspaces")}
                    className="mt-6 text-primary font-bold hover:underline flex items-center gap-2 mx-auto"
                >
                    <ChevronLeft className="h-4 w-4" /> Back to Workspaces
                </button>
            </div>
        );
    }

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <div className="flex items-center gap-4 mb-8">
                <button
                    onClick={() => navigate("/workspaces")}
                    className="p-2 hover:bg-secondary rounded-xl transition-colors"
                >
                    <ChevronLeft className="h-6 w-6" />
                </button>
                <div>
                    <div className="flex items-center gap-3">
                        <h1 className="text-3xl font-black tracking-tight">{workspace.name}</h1>
                        <button
                            onClick={() => toggleMutation.mutate()}
                            disabled={toggleMutation.isPending}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1 rounded-full transition-all hover:scale-105 active:scale-95 disabled:opacity-50",
                                workspace.is_active ? "bg-green-50 text-green-700 font-bold border border-green-200" : "bg-gray-100 text-gray-500 font-bold border border-gray-200"
                            )}
                        >
                            <span className={cn(
                                "w-2 h-2 rounded-full",
                                workspace.is_active ? "bg-green-500 animate-pulse" : "bg-gray-300"
                            )} />
                            <span className="text-[10px] uppercase tracking-tight">
                                {workspace.is_active ? "Live" : "Draft"}
                            </span>
                        </button>
                    </div>
                    <p className="text-muted-foreground font-medium">Manage environment settings and automation flows.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                {/* Main Configuration */}
                <div className="lg:col-span-8 space-y-8">
                    <div className="bg-card border rounded-2xl shadow-sm overflow-hidden">
                        <div className="p-6 border-b bg-gray-50/50 flex justify-between items-center">
                            <div className="flex items-center gap-2">
                                <Settings2 className="h-5 w-5 text-primary" />
                                <h2 className="text-lg font-bold">Workspace Settings</h2>
                            </div>
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => {
                                        if (confirm("Are you sure you want to delete this workspace? This cannot be undone.")) {
                                            deleteMutation.mutate(id!);
                                        }
                                    }}
                                    className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                                    title="Delete Workspace"
                                >
                                    <Trash2 className="h-5 w-5" />
                                </button>
                                <button
                                    onClick={() => updateMutation.mutate({ id: id!, data: formData })}
                                    disabled={updateMutation.isPending || !formData.name}
                                    className="bg-primary text-primary-foreground px-6 py-2 rounded-xl font-bold flex items-center gap-2 hover:scale-[1.02] active:scale-[0.98] transition-all shadow-lg shadow-primary/25 disabled:opacity-50"
                                >
                                    <Save className="h-4 w-4" />
                                    {updateMutation.isPending ? "Saving..." : "Save Changes"}
                                </button>
                            </div>
                        </div>

                        <div className="p-8 space-y-8 h-[70vh] overflow-y-auto custom-scrollbar">
                            {/* Basic Info */}
                            <section className="space-y-4">
                                <div className="flex items-center gap-2 mb-2">
                                    <div className="p-1.5 bg-blue-50 text-blue-600 rounded-lg"><Target className="h-4 w-4" /></div>
                                    <h3 className="font-bold text-sm uppercase tracking-wider text-gray-600">Core Identity</h3>
                                </div>
                                <div className="grid grid-cols-2 gap-6">
                                    <div className="space-y-2">
                                        <label className="text-sm font-bold text-gray-500">Workspace Name</label>
                                        <input
                                            value={formData.name}
                                            onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                            placeholder="e.g. Sales Support Bot"
                                            className="w-full bg-secondary/50 border-transparent focus:bg-white focus:ring-2 focus:ring-primary/20 rounded-xl p-3 text-sm font-medium transition-all"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-sm font-bold text-gray-500">Knowledge Base (Source)</label>
                                        <select
                                            value={formData.knowledge_base_id}
                                            onChange={e => setFormData(prev => ({ ...prev, knowledge_base_id: e.target.value }))}
                                            className="w-full bg-secondary/50 border-transparent focus:bg-white focus:ring-2 focus:ring-primary/20 rounded-xl p-3 text-sm font-medium transition-all"
                                        >
                                            <option value="">No Knowledge Base (LLM only)</option>
                                            {collectionsData?.collections?.map((c: any) => (
                                                <option key={c.id} value={c.id}>{c.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                            </section>

                            {/* Prompts */}
                            <section className="space-y-4">
                                <div className="flex items-center gap-2 mb-2">
                                    <div className="p-1.5 bg-purple-50 text-purple-600 rounded-lg"><Bot className="h-4 w-4" /></div>
                                    <h3 className="font-bold text-sm uppercase tracking-wider text-gray-600">AI Personality</h3>
                                </div>
                                <div className="space-y-4">
                                    <div className="space-y-2">
                                        <label className="text-sm font-bold text-gray-500 italic flex items-center gap-1.5">
                                            System Prompt <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded not-italic font-black text-gray-400">INSTRUCTIONS</span>
                                        </label>
                                        <textarea
                                            rows={6}
                                            value={formData.system_prompt}
                                            onChange={e => setFormData(prev => ({ ...prev, system_prompt: e.target.value }))}
                                            placeholder="Instructions for the AI..."
                                            className="w-full bg-secondary/30 border-transparent focus:bg-white focus:ring-2 focus:ring-primary/20 rounded-xl p-4 text-sm font-medium transition-all resize-none"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <div className="flex justify-between items-end">
                                            <label className="text-sm font-bold text-gray-500 italic flex items-center gap-1.5">
                                                User Prompt Template <span className="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded not-italic font-black text-gray-400">STRUCTURE</span>
                                            </label>
                                            <p className="text-[10px] text-gray-400 font-bold mb-1">Variables: <code className="bg-gray-100 p-0.5">{"{{body}}"}</code>, <code className="bg-gray-100 p-0.5">{"{{rag_result}}"}</code></p>
                                        </div>
                                        <textarea
                                            rows={4}
                                            value={formData.user_prompt_template}
                                            onChange={e => setFormData(prev => ({ ...prev, user_prompt_template: e.target.value }))}
                                            className="w-full bg-secondary/30 border-transparent focus:bg-white focus:ring-2 focus:ring-primary/20 rounded-xl p-4 text-sm font-medium transition-all resize-none"
                                        />
                                    </div>
                                </div>
                            </section>

                            {/* Group Selection */}
                            <section className="space-y-4">
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className="p-1.5 bg-green-50 text-green-600 rounded-lg"><MessageSquare className="h-4 w-4" /></div>
                                        <h3 className="font-bold text-sm uppercase tracking-wider text-gray-600">Deployment Grounds</h3>
                                    </div>
                                    <button
                                        onClick={() => syncGroupsMutation.mutate()}
                                        disabled={syncGroupsMutation.isPending}
                                        className="text-[10px] font-black uppercase tracking-widest text-primary flex items-center gap-1.5 bg-primary/5 px-2 py-1 rounded-lg hover:bg-primary/10 transition-colors"
                                    >
                                        {syncGroupsMutation.isPending ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <RefreshCw className="h-2.5 w-2.5" />}
                                        Sync Groups
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                    {groupsData?.groups?.map((group: any) => (
                                        <div
                                            key={group.id}
                                            onClick={() => toggleGroupSelection(group.id)}
                                            className={cn(
                                                "p-3 rounded-xl border-2 cursor-pointer transition-all flex items-center gap-2",
                                                formData.group_ids.includes(group.id)
                                                    ? "border-primary/60 bg-primary/5"
                                                    : "border-gray-100 hover:border-gray-200"
                                            )}
                                        >
                                            {formData.group_ids.includes(group.id) ? (
                                                <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
                                            ) : (
                                                <div className="h-4 w-4 rounded-full border-2 border-gray-200 shrink-0" />
                                            )}
                                            <span className="text-xs font-bold truncate">{group.name}</span>
                                        </div>
                                    ))}
                                </div>
                            </section>
                        </div>
                    </div>
                </div>

                {/* Sidebar: Logic Layers */}
                <div className="lg:col-span-4 space-y-6">
                    <div className="bg-card border rounded-2xl shadow-sm p-6">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-2">
                                <Zap className="h-5 w-5 text-yellow-500" />
                                <h3 className="font-bold">Logic Layers</h3>
                            </div>
                            <button
                                onClick={handleAddFlow}
                                disabled={createFlowMutation.isPending}
                                className="p-1.5 bg-primary/5 text-primary rounded-lg hover:bg-primary/10 transition-colors"
                            >
                                <Plus className="h-4 w-4" />
                            </button>
                        </div>

                        <div className="space-y-3">
                            {flowsData?.flows?.map((flow: any) => (
                                <div key={flow.id} className="p-4 rounded-xl border bg-secondary/5 flex items-center justify-between group transition-all hover:bg-secondary/10 hover:border-primary/30">
                                    <div className="min-w-0">
                                        <h4 className="font-bold text-sm truncate">{flow.name}</h4>
                                        <p className="text-[10px] font-medium text-gray-400">Trigger: {flow.trigger_type}</p>
                                    </div>
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={() => deleteFlowMutation.mutate(flow.id)}
                                            className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                        <button
                                            onClick={() => navigate(`/flows/${flow.id}`)}
                                            className="p-1.5 text-primary hover:bg-primary/10 rounded-lg transition-colors"
                                        >
                                            <ArrowRight className="h-3.5 w-3.5" />
                                        </button>
                                    </div>
                                </div>
                            ))}

                            {flowsData?.flows?.length === 0 && (
                                <div className="py-8 text-center border-2 border-dashed rounded-xl bg-gray-50/50">
                                    <p className="text-[10px] font-bold text-gray-400">No custom layers</p>
                                </div>
                            )}

                            {flowsLoading && (
                                <div className="flex justify-center py-4">
                                    <Loader2 className="h-4 w-4 animate-spin text-primary/40" />
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="bg-primary/5 rounded-2xl p-6 border border-primary/10">
                        <h4 className="text-xs font-black uppercase tracking-widest text-primary mb-2">Pro Tip</h4>
                        <p className="text-xs text-primary/70 font-medium leading-relaxed">
                            Logic Layers take precedence over RAG. Use them for specific keywords, command handling, or integrations.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
