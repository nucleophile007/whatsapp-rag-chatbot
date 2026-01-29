import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getWorkspaces, createWorkspace, getCollections, toggleWorkspace } from "../lib/api";
import { Loader2, Plus, Layout, Bot, Save, ChevronRight, Power } from "lucide-react";
import { cn } from "../lib/utils";
import { useNavigate } from "react-router-dom";

export default function Workspaces() {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const [isCreating, setIsCreating] = useState(false);

    // Form State (Only for Create Modal/Section)
    const [formData, setFormData] = useState({
        name: "",
        knowledge_base_id: "",
        system_prompt: "You are a helpful assistant. Use the following context to answer questions.",
        user_prompt_template: "Question: {{body}}\n\nContext: {{rag_result}}",
        group_ids: [] as string[]
    });

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
            resetForm();
            if (newWs?.id) {
                navigate(`/workspaces/${newWs.id}`);
            }
        },
    });

    const toggleMutation = useMutation({
        mutationFn: toggleWorkspace,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["workspaces"] });
        },
    });

    const resetForm = () => {
        setFormData({
            name: "",
            knowledge_base_id: "",
            system_prompt: "You are a helpful assistant. Use the following context to answer questions.",
            user_prompt_template: "Question: {{body}}\n\nContext: {{rag_result}}",
            group_ids: []
        });
    };

    if (wsLoading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-primary" /></div>;
    }

    return (
        <div className="p-8 max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-4xl font-black tracking-tight flex items-center gap-3">
                        <Layout className="h-10 w-10 text-primary" />
                        Workspaces
                    </h1>
                    <p className="text-muted-foreground mt-2 font-medium">Manage your bot fleets and their intelligence layers.</p>
                </div>
                {!isCreating && (
                    <button
                        onClick={() => { resetForm(); setIsCreating(true); }}
                        className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-3 rounded-2xl font-bold hover:scale-[1.03] active:scale-[0.97] transition-all shadow-xl shadow-primary/20"
                    >
                        <Plus className="h-5 w-5" />
                        New Workspace
                    </button>
                )}
            </div>

            {isCreating ? (
                <div className="max-w-3xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-300">
                    <div className="bg-card border rounded-3xl shadow-2xl overflow-hidden">
                        <div className="p-8 border-b bg-gray-50/50 flex justify-between items-center">
                            <div>
                                <h2 className="text-2xl font-black">Build New Workspace</h2>
                                <p className="text-sm text-muted-foreground font-medium">Set the foundation for your new AI agent.</p>
                            </div>
                            <button
                                onClick={() => setIsCreating(false)}
                                className="text-sm font-bold text-gray-400 hover:text-gray-600 px-4 py-2 hover:bg-gray-100 rounded-xl transition-all"
                            >
                                Cancel
                            </button>
                        </div>

                        <div className="p-8 space-y-8">
                            <div className="space-y-6">
                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-gray-500">Workspace Name</label>
                                    <input
                                        value={formData.name}
                                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                        placeholder="e.g. Customer Support Bot"
                                        className="w-full bg-secondary/30 border-2 border-transparent focus:border-primary/20 focus:bg-white focus:ring-4 focus:ring-primary/5 rounded-2xl p-4 text-lg font-bold transition-all"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-gray-500">Assign Knowledge Base</label>
                                    <select
                                        value={formData.knowledge_base_id}
                                        onChange={e => setFormData(prev => ({ ...prev, knowledge_base_id: e.target.value }))}
                                        className="w-full bg-secondary/30 border-2 border-transparent focus:border-primary/20 focus:bg-white focus:ring-4 focus:ring-primary/5 rounded-2xl p-4 font-bold transition-all"
                                    >
                                        <option value="">No Knowledge Base (LLM only)</option>
                                        {collectionsData?.collections?.map((c: any) => (
                                            <option key={c.id} value={c.id}>{c.name}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <button
                                onClick={() => createMutation.mutate(formData)}
                                disabled={createMutation.isPending || !formData.name}
                                className="w-full bg-primary text-primary-foreground py-5 rounded-2xl font-black text-lg flex items-center justify-center gap-3 hover:scale-[1.01] active:scale-[0.99] transition-all shadow-2xl shadow-primary/30 disabled:opacity-50"
                            >
                                {createMutation.isPending ? <Loader2 className="h-6 w-6 animate-spin" /> : <Save className="h-6 w-6" />}
                                {createMutation.isPending ? "Creating Workspace..." : "Initialize Workspace"}
                            </button>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {workspacesData?.workspaces?.map((ws: any) => (
                        <div
                            key={ws.id}
                            onClick={() => navigate(`/workspaces/${ws.id}`)}
                            className="group p-6 rounded-3xl border bg-card cursor-pointer transition-all hover:border-primary hover:shadow-2xl hover:shadow-primary/5 flex flex-col h-full relative"
                        >
                            <div className="flex items-start justify-between mb-6">
                                <div className="h-14 w-14 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:bg-primary group-hover:scale-110 transition-all duration-300">
                                    <Bot className="h-7 w-7 text-primary group-hover:text-primary-foreground transition-colors" />
                                </div>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        toggleMutation.mutate(ws.id);
                                    }}
                                    disabled={toggleMutation.isPending}
                                    className={cn(
                                        "flex items-center gap-1.5 px-3 py-1.5 rounded-full transition-all hover:scale-105 active:scale-95 disabled:opacity-50",
                                        ws.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                                    )}
                                >
                                    <span className={cn(
                                        "w-2 h-2 rounded-full",
                                        ws.is_active ? "bg-green-500 animate-pulse" : "bg-gray-300"
                                    )} />
                                    <span className="text-[10px] font-black uppercase tracking-tight">
                                        {ws.is_active ? "Live" : "Draft"}
                                    </span>
                                </button>
                            </div>

                            <div className="flex-1">
                                <h3 className="font-black text-xl mb-2 group-hover:text-primary transition-colors">{ws.name}</h3>
                                <div className="flex flex-wrap gap-1.5 mb-6">
                                    {ws.groups?.map((g: any) => (
                                        <span key={g.id} className="text-[10px] bg-secondary px-2.5 py-1 rounded-lg font-bold text-gray-600">#{g.name}</span>
                                    ))}
                                    {ws.groups?.length === 0 && <span className="text-[10px] text-gray-400 italic">No groups connected</span>}
                                </div>
                            </div>

                            <div className="mt-auto pt-6 border-t border-dashed flex items-center justify-between">
                                <span className="text-xs font-bold text-gray-400">
                                    {ws.knowledge_base ? ws.knowledge_base.name : "Pure Intelligence"}
                                </span>
                                <ChevronRight className="h-5 w-5 text-gray-300 group-hover:text-primary group-hover:translate-x-1 transition-all" />
                            </div>
                        </div>
                    ))}

                    {workspacesData?.workspaces?.length === 0 && (
                        <div className="col-span-full py-20 text-center border-4 border-dashed rounded-3xl bg-gray-50/50">
                            <Bot className="h-20 w-20 text-gray-200 mx-auto mb-6" />
                            <h3 className="text-2xl font-black text-gray-400">Zero Workspaces</h3>
                            <p className="text-gray-400 font-medium mt-2">Time to build your first autonomous environment.</p>
                            <button
                                onClick={() => setIsCreating(true)}
                                className="mt-8 bg-white border-2 border-gray-200 px-8 py-3 rounded-2xl font-black text-gray-400 hover:border-primary hover:text-primary transition-all"
                            >
                                Start Building
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// Add CSS for thin scrollbar
const style = document.createElement('style');
style.textContent = `
    .custom-scrollbar::-webkit-scrollbar { width: 4px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 10px; }
    .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #d1d5db; }
`;
document.head.appendChild(style);
