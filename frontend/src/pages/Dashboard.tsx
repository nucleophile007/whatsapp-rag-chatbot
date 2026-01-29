import { Layers, Database, Users, Sparkles } from "lucide-react";

export default function Dashboard() {
    return (
        <div className="p-8 max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
            <div className="flex items-center gap-4">
                <div className="h-16 w-16 bg-primary rounded-2xl flex items-center justify-center text-white shadow-xl shadow-primary/20">
                    <Sparkles className="h-8 w-8" />
                </div>
                <div>
                    <h1 className="text-4xl font-black tracking-tight text-gray-900">AI Workspace</h1>
                    <p className="text-lg text-muted-foreground font-medium">Empower your WhatsApp groups with RAG-driven intelligence.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8">
                <div className="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md transition-shadow">
                    <Layers className="h-6 w-6 text-primary mb-4" />
                    <h3 className="font-bold text-lg">Workspaces</h3>
                    <p className="text-sm text-muted-foreground mt-2">Manage your bot's logic and deployment.</p>
                </div>
                <div className="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md transition-shadow">
                    <Database className="h-6 w-6 text-primary mb-4" />
                    <h3 className="font-bold text-lg">Knowledge Base</h3>
                    <p className="text-sm text-muted-foreground mt-2">Index documents and synced data.</p>
                </div>
                <div className="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md transition-shadow">
                    <Users className="h-6 w-6 text-primary mb-4" />
                    <h3 className="font-bold text-lg">Groups</h3>
                    <p className="text-sm text-muted-foreground mt-2">Manage connected communities.</p>
                </div>
            </div>
        </div>
    );
}
