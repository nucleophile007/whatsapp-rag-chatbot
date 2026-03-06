import { Handle, Position, type NodeProps } from "reactflow";
import type { LucideIcon } from "lucide-react";
import { Zap, MessageSquare, GitBranch, Play, Search, Send, FileText, Globe, Clock, CalendarClock } from "lucide-react";
import { cn } from "../lib/utils";
import type { FlowNodeData } from "../lib/flowSchema";

const ICONS: Record<string, LucideIcon> = {
  trigger: Zap,
  action: Play,
  condition: GitBranch,
  whatsapp_message: MessageSquare,
  whatsapp_mention: MessageSquare,
  rag_query: Search,
  send_whatsapp_message: Send,
  text_contains: FileText,
  text_not_empty: FileText,
  delay: Clock,
  http_request: Globe,
  schedule: CalendarClock,
};

const TYPE_STYLES: Record<string, string> = {
  trigger: "border-cyan-200 bg-cyan-50/80",
  condition: "border-amber-200 bg-amber-50/80",
  action: "border-emerald-200 bg-emerald-50/80",
};

const ICON_STYLES: Record<string, string> = {
  trigger: "bg-cyan-600",
  condition: "bg-amber-600",
  action: "bg-emerald-600",
};

export default function CustomNode({ data, selected }: NodeProps<FlowNodeData>) {
  if (!data) return null;
  const Icon = ICONS[data.subType || ""] || ICONS[data.type] || Zap;

  return (
    <div
      className={cn(
        "relative min-w-[210px] rounded-xl border px-4 py-3 shadow-sm transition-all",
        TYPE_STYLES[data.type] || "border-slate-200 bg-white",
        selected && "ring-2 ring-primary/30"
      )}
    >
      <div className="flex items-center gap-3">
        <div className={cn("h-8 w-8 rounded-lg flex items-center justify-center text-white", ICON_STYLES[data.type] || "bg-slate-700")}>
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-bold text-slate-900">{data.label || "Unnamed Node"}</div>
          <div className="text-xs capitalize text-slate-500">{data.subType?.replace(/_/g, " ") || data.type || "Custom"}</div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className={cn("h-3 w-3 border-2 border-white bg-slate-400", data.type === "trigger" && "invisible")}
      />

      {data.type === "condition" ? (
        <>
          <Handle
            type="source"
            position={Position.Bottom}
            id="true"
            className="h-3 w-3 border-2 border-white bg-emerald-500"
            style={{ left: "30%" }}
          />
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            className="h-3 w-3 border-2 border-white bg-rose-500"
            style={{ left: "70%" }}
          />
          <div className="pointer-events-none mt-2 flex justify-between px-3 text-[10px] font-semibold uppercase tracking-wide">
            <span className="text-emerald-700">True</span>
            <span className="text-rose-700">False</span>
          </div>
        </>
      ) : (
        <Handle type="source" position={Position.Bottom} className="h-3 w-3 border-2 border-white bg-slate-400" />
      )}
    </div>
  );
}
