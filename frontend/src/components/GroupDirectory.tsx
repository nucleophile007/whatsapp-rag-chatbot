import { useQuery } from "@tanstack/react-query";
import { getGroups } from "../lib/api";
import { Loader2, Copy, X, Hash, Search } from "lucide-react";
import { useState } from "react";

interface GroupDirectoryProps {
    onClose: () => void;
}

export default function GroupDirectory({ onClose }: GroupDirectoryProps) {
    const [searchQuery, setSearchQuery] = useState("");
    const { data, isLoading } = useQuery({
        queryKey: ["groups"],
        queryFn: getGroups
    });

    const copyId = (id: string) => {
        navigator.clipboard.writeText(id);
        alert("Copied: " + id);
    };

    const filteredGroups = data?.groups?.filter((g: any) =>
        g.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        g.chat_id.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-end">
            <div className="bg-white w-96 h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                <div className="p-4 border-b flex justify-between items-center bg-gray-50">
                    <div className="flex items-center gap-2 font-bold">
                        <Hash className="h-4 w-4 text-primary" />
                        Group Directory
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    <p className="text-xs text-muted-foreground mb-4">
                        Quickly find and copy Group IDs for use in your nodes (e.g., Send Message chat_id).
                    </p>

                    <div className="relative mb-4">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="Search name or ID..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="h-9 w-full rounded-md border border-input bg-gray-50/50 pl-9 pr-3 py-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                        />
                    </div>

                    {isLoading ? (
                        <div className="flex justify-center p-8"><Loader2 className="animate-spin text-primary" /></div>
                    ) : (
                        filteredGroups?.map((group: any) => (
                            <div key={group.id} className="p-3 border rounded-lg hover:border-primary group transition-all">
                                <div className="flex justify-between items-start mb-1">
                                    <span className="font-semibold text-sm truncate pr-2">{group.name}</span>
                                    <span className={`text-[10px] px-1.5 rounded ${group.is_enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                                        {group.is_enabled ? 'Active' : 'Off'}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between gap-2 mt-2 bg-gray-50 p-2 rounded border border-dashed">
                                    <code className="text-[10px] text-gray-600 truncate">{group.chat_id}</code>
                                    <button
                                        onClick={() => copyId(group.chat_id)}
                                        className="text-primary hover:bg-primary/10 p-1 rounded"
                                    >
                                        <Copy className="h-3 w-3" />
                                    </button>
                                </div>
                            </div>
                        ))
                    )}

                    {data?.groups?.length === 0 && !isLoading && (
                        <div className="text-center py-12 text-muted-foreground text-sm">
                            No groups found. Sync in Groups Manager first.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
