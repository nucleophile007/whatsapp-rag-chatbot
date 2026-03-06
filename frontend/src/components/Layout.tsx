import { Link, Outlet, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Database,
  Layers,
  Workflow,
  Sparkles,
  ChevronRight,
  Code2,
} from "lucide-react";
import { cn } from "../lib/utils";

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard, info: "Overview" },
  { name: "Workspaces", href: "/workspaces", icon: Layers, info: "AI environments" },
  { name: "Logic Layers", href: "/logic-layers", icon: Workflow, info: "All automations" },
  { name: "Knowledge", href: "/knowledge-base", icon: Database, info: "Documents" },
  { name: "Client API", href: "/client-api", icon: Code2, info: "Chat endpoint + docs" },
  { name: "Executions", href: "/executions", icon: FileText, info: "Runtime logs" },
];

function isActivePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function getCurrentLabel(pathname: string) {
  const navItem = navigation.find((item) => isActivePath(pathname, item.href));
  if (navItem) return navItem.name;
  if (pathname.startsWith("/flows/")) return "Flow Builder";
  return "Workspace";
}

export default function Layout() {
  const location = useLocation();
  const currentLabel = getCurrentLabel(location.pathname);

  return (
    <div className="min-h-screen p-3 md:p-5">
      <div className="app-shell mx-auto flex min-h-[calc(100vh-24px)] max-w-[1500px] overflow-hidden md:min-h-[calc(100vh-40px)]">
        <aside className="hidden w-72 shrink-0 border-r border-border/60 bg-white/80 p-5 lg:flex lg:flex-col">
          <Link to="/" className="mb-8 flex items-center gap-3">
            <div className="animate-float flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-600 to-teal-500 text-white shadow-lg">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Async RAG</p>
              <h1 className="text-lg font-bold">Command Center</h1>
            </div>
          </Link>

          <nav className="space-y-1.5">
            {navigation.map((item, index) => {
              const active = isActivePath(location.pathname, item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  style={{ animationDelay: `${index * 60}ms` }}
                  className={cn(
                    "animate-rise group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all",
                    active
                      ? "bg-primary text-primary-foreground shadow-md"
                      : "hover:bg-secondary text-muted-foreground hover:text-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold">{item.name}</p>
                    <p
                      className={cn(
                        "text-[11px]",
                        active ? "text-primary-foreground/80" : "text-muted-foreground"
                      )}
                    >
                      {item.info}
                    </p>
                  </div>
                  <ChevronRight className={cn("h-3.5 w-3.5", !active && "opacity-0 group-hover:opacity-100")} />
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 items-center justify-between border-b border-border/60 bg-white/70 px-4 backdrop-blur md:px-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Workspace Surface</p>
              <h2 className="text-lg font-bold md:text-xl">{currentLabel}</h2>
            </div>
            <div className="tag bg-accent text-accent-foreground">
              <span className="h-2 w-2 rounded-full bg-teal-500" />
              Live System
            </div>
          </header>

          <main className="min-h-0 flex-1 overflow-auto pb-20 lg:pb-0">
            <Outlet />
          </main>
        </div>

        <nav className="fixed bottom-3 left-1/2 z-20 flex -translate-x-1/2 gap-1 rounded-2xl border bg-white/92 p-1 shadow-xl backdrop-blur lg:hidden">
          {navigation.map((item) => {
            const active = isActivePath(location.pathname, item.href);
            return (
              <Link
                key={item.name}
                to={item.href}
                className={cn(
                  "flex min-w-[74px] flex-col items-center gap-1 rounded-xl px-2 py-2 text-[11px] font-semibold",
                  active ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
