import { Link, Outlet, useLocation } from "react-router-dom";
import { LayoutDashboard, FileText, Database, Layers } from "lucide-react";
import { cn } from "../lib/utils";

const navigation = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Workspaces", href: "/workspaces", icon: Layers },
    { name: "Knowledge Base", href: "/knowledge-base", icon: Database },
    { name: "Executions", href: "/executions", icon: FileText },
];

export default function Layout() {
    const location = useLocation();

    return (
        <div className="flex h-screen bg-gray-50/50">
            {/* Sidebar */}
            <div className="hidden border-r bg-gray-100/40 lg:block lg:w-64">
                <div className="flex h-full flex-col">
                    <div className="flex h-14 items-center border-b px-6">
                        <Link to="/" className="flex items-center gap-2 font-semibold">
                            <span className="h-6 w-6 rounded-lg bg-primary text-white flex items-center justify-center font-bold">
                                A
                            </span>
                            <span>AI Workspace</span>
                        </Link>
                    </div>
                    <div className="flex-1 overflow-auto py-2">
                        <nav className="grid items-start px-4 text-sm font-medium">
                            {navigation.map((item) => (
                                <Link
                                    key={item.name}
                                    to={item.href}
                                    className={cn(
                                        "flex items-center gap-3 rounded-lg px-3 py-2 transition-all hover:text-primary",
                                        location.pathname === item.href
                                            ? "bg-gray-100 text-primary"
                                            : "text-muted-foreground"
                                    )}
                                >
                                    <item.icon className="h-4 w-4" />
                                    {item.name}
                                </Link>
                            ))}
                        </nav>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex flex-1 flex-col overflow-hidden">
                <header className="flex h-14 items-center gap-4 border-b bg-gray-100/40 px-6 lg:h-[60px]">
                    <div className="flex-1">
                        <h1 className="font-semibold text-lg">
                            {navigation.find((n) => n.href === location.pathname)?.name || "Dashboard"}
                        </h1>
                    </div>
                </header>
                <main className="flex-1 overflow-auto">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
