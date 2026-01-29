import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCollections, createCollection, uploadDocuments, syncCollections } from "../lib/api";
import { Loader2, Plus, Database, FileUp, CheckCircle, AlertCircle, FileText, RefreshCcw, HelpCircle } from "lucide-react";
import { cn } from "../lib/utils";

export default function KnowledgeBase() {
    const queryClient = useQueryClient();
    const [isCreating, setIsCreating] = useState(false);
    const [newName, setNewName] = useState("");
    const [selectedKb, setSelectedKb] = useState<any>(null);
    const [files, setFiles] = useState<File[]>([]);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');

    const { data, isLoading } = useQuery({
        queryKey: ["collections"],
        queryFn: getCollections,
    });

    const createMutation = useMutation({
        mutationFn: createCollection,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["collections"] });
            setIsCreating(false);
            setNewName("");
        },
    });

    const uploadMutation = useMutation({
        mutationFn: (vars: { name: string; files: File[] }) => uploadDocuments(vars.name, vars.files),
        onMutate: () => setUploadStatus('uploading'),
        onSuccess: () => {
            setUploadStatus('success');
            setFiles([]);
            setTimeout(() => setUploadStatus('idle'), 3000);
        },
        onError: () => setUploadStatus('error'),
    });

    const syncMutation = useMutation({
        mutationFn: syncCollections,
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ["collections"] });
            setSyncStatus(`Sync done! Found ${data.total_found} collections.`);
            setTimeout(() => setSyncStatus(""), 4000);
        },
    });

    const [syncStatus, setSyncStatus] = useState("");

    // Auto-select first collection if none selected
    if (!selectedKb && data?.collections?.length > 0) {
        setSelectedKb(data.collections[0]);
    }

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles(Array.from(e.target.files));
        }
    };

    if (isLoading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-primary" /></div>;
    }

    return (
        <div className="p-8 max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Knowledge Base</h1>
                    <p className="text-muted-foreground mt-1">Manage document collections for your RAG Workspaces.</p>
                </div>
                <div className="flex gap-3">
                    {syncStatus && (
                        <div className="flex items-center gap-2 text-xs font-bold text-primary bg-primary/10 px-3 rounded-lg animate-in slide-in-from-right-2">
                            <CheckCircle className="h-3 w-3" />
                            {syncStatus}
                        </div>
                    )}
                    <button
                        onClick={() => syncMutation.mutate()}
                        disabled={syncMutation.isPending}
                        className="flex items-center gap-2 bg-secondary text-secondary-foreground px-4 py-2 rounded-lg hover:bg-secondary/80 transition-colors border shadow-sm"
                        title="Scan Qdrant for existing collections"
                    >
                        <RefreshCcw className={cn("h-4 w-4", syncMutation.isPending && "animate-spin")} />
                        Sync Qdrant
                    </button>
                    <button
                        onClick={() => setIsCreating(true)}
                        className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary/90 transition-colors shadow-md shadow-primary/20"
                    >
                        <Plus className="h-4 w-4" />
                        New Collection
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Collections List */}
                <div className="md:col-span-1 space-y-4">
                    <div className="flex items-center justify-between mb-2">
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">Collections</h2>
                        <div className="group relative">
                            <HelpCircle className="h-4 w-4 text-gray-300 cursor-help" />
                            <div className="absolute right-0 w-64 p-3 bg-white border rounded-xl shadow-xl hidden group-hover:block z-50 text-xs text-gray-500 normal-case leading-relaxed animate-in fade-in zoom-in-95">
                                <p className="font-bold mb-1 text-gray-700">How to use:</p>
                                <ol className="list-decimal list-inside space-y-1">
                                    <li>Create a <b>Collection</b> (this creates it in Qdrant).</li>
                                    <li>Select it from this list.</li>
                                    <li>Upload <b>PDFs</b> and click "Index".</li>
                                    <li>This "syncs" your documents into Qdrant.</li>
                                </ol>
                            </div>
                        </div>
                    </div>
                    {data?.collections?.map((kb: any) => (
                        <div
                            key={kb.id}
                            onClick={() => setSelectedKb(kb)}
                            className={cn(
                                "p-4 rounded-xl border cursor-pointer transition-all hover:border-primary/50 flex items-center gap-3",
                                selectedKb?.id === kb.id ? "bg-primary/5 border-primary shadow-sm" : "bg-card"
                            )}
                        >
                            <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center">
                                <Database className="h-5 w-5 text-primary" />
                            </div>
                            <div className="flex-1 truncate">
                                <h3 className="font-medium truncate">{kb.name}</h3>
                                <p className="text-xs text-muted-foreground">Created {new Date(kb.created_at).toLocaleDateString()}</p>
                            </div>
                        </div>
                    ))}

                    {data?.collections?.length === 0 && !isCreating && (
                        <div className="text-center py-8 border border-dashed rounded-xl grayscale opacity-50">
                            <p className="text-sm italic">No collections yet</p>
                        </div>
                    )}

                    {isCreating && (
                        <div className="p-4 rounded-xl border bg-primary/5 border-primary animate-in fade-in slide-in-from-top-2">
                            <input
                                autoFocus
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                placeholder="Collection name..."
                                className="w-full bg-transparent border-none focus:ring-0 p-0 font-medium placeholder:text-gray-300"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') createMutation.mutate({ name: newName });
                                    if (e.key === 'Escape') setIsCreating(false);
                                }}
                            />
                            <div className="flex justify-end gap-2 mt-3">
                                <button onClick={() => setIsCreating(false)} className="text-xs hover:underline">Cancel</button>
                                <button
                                    onClick={() => createMutation.mutate({ name: newName })}
                                    disabled={!newName || createMutation.isPending}
                                    className="text-xs font-bold text-primary"
                                >
                                    {createMutation.isPending ? "Creating..." : "Save"}
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Collection Detail / Upload */}
                <div className="md:col-span-2">
                    {selectedKb ? (
                        <div className="bg-card border rounded-2xl shadow-sm overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                            <div className="p-6 border-b bg-gray-50/50 flex justify-between items-center">
                                <div>
                                    <h2 className="text-xl font-bold">{selectedKb.name}</h2>
                                    <p className="text-sm text-muted-foreground">{selectedKb.description || "Knowledge base for your bot."}</p>
                                </div>
                                <div className="h-10 w-10 rounded-full bg-white border flex items-center justify-center text-primary shadow-xs">
                                    <Database className="h-5 w-5" />
                                </div>
                            </div>

                            <div className="p-8">
                                <div className="border-2 border-dashed border-gray-200 rounded-2xl p-10 text-center hover:border-primary/30 transition-colors bg-gray-50/30">
                                    <div className="mx-auto w-16 h-16 bg-white rounded-2xl shadow-sm border flex items-center justify-center mb-4">
                                        <FileUp className="h-8 w-8 text-primary" />
                                    </div>
                                    <h3 className="text-lg font-semibold">Upload PDF Documents</h3>
                                    <p className="text-sm text-muted-foreground mt-1 max-w-xs mx-auto">
                                        Select multiple PDFs to index into this collection. They will be chunked and stored as vectors.
                                    </p>

                                    <input
                                        type="file"
                                        multiple
                                        accept=".pdf"
                                        onChange={handleFileChange}
                                        className="hidden"
                                        id="file-upload"
                                    />
                                    <label
                                        htmlFor="file-upload"
                                        className="mt-6 inline-flex items-center gap-2 bg-white border px-4 py-2 rounded-lg cursor-pointer hover:bg-gray-50 shadow-sm transition-all"
                                    >
                                        <Plus className="h-4 w-4" />
                                        Select Files
                                    </label>

                                    {files.length > 0 && (
                                        <div className="mt-8 space-y-2 text-left max-w-md mx-auto">
                                            <div className="text-xs font-bold text-gray-400 uppercase flex justify-between">
                                                <span>Queue ({files.length})</span>
                                                <button onClick={() => setFiles([])} className="text-destructive hover:underline normal-case">Clear all</button>
                                            </div>
                                            {files.map((f: File, i: number) => (
                                                <div key={i} className="flex items-center gap-2 bg-white p-2 rounded-lg border text-sm animate-in slide-in-from-left duration-200" style={{ animationDelay: `${i * 50}ms` }}>
                                                    <FileText className="h-4 w-4 text-primary shrink-0" />
                                                    <span className="flex-1 truncate">{f.name}</span>
                                                    <span className="text-[10px] text-gray-400">{(f.size / 1024).toFixed(0)} KB</span>
                                                </div>
                                            ))}

                                            <button
                                                onClick={() => uploadMutation.mutate({ name: selectedKb.name, files })}
                                                disabled={uploadStatus === 'uploading'}
                                                className="w-full mt-6 bg-primary text-primary-foreground py-3 rounded-xl font-bold flex items-center justify-center gap-2 shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50 disabled:grayscale"
                                            >
                                                {uploadStatus === 'uploading' ? (
                                                    <><Loader2 className="h-5 w-5 animate-spin" /> Indexing Documents...</>
                                                ) : (
                                                    <><FileUp className="h-5 w-5" /> Start Indexing</>
                                                )}
                                            </button>
                                        </div>
                                    )}

                                    {uploadStatus === 'success' && (
                                        <div className="mt-6 flex items-center justify-center gap-2 text-green-600 font-medium animate-in zoom-in-50">
                                            <CheckCircle className="h-5 w-5" />
                                            Indexing complete!
                                        </div>
                                    )}
                                    {uploadStatus === 'error' && (
                                        <div className="mt-6 flex items-center justify-center gap-2 text-destructive font-medium animate-in shake-in">
                                            <AlertCircle className="h-5 w-5" />
                                            Upload failed. Check logs.
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center p-12 border border-dashed rounded-2xl bg-gray-50/20 grayscale">
                            <Database className="h-12 w-12 text-gray-300 mb-4" />
                            <h3 className="text-lg font-medium text-gray-400">Select a collection</h3>
                            <p className="text-sm text-gray-300 max-w-xs mt-2">Choose a collection from the left or create a new one to start indexing documents.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
