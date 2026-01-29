import { Handle, Position, type NodeProps } from "reactflow";
import { Zap, MessageSquare, GitBranch, Play, Search, Send, FileText, Globe, Clock } from "lucide-react";
import { cn } from "../lib/utils";

const ICONS: Record<string, any> = {
    trigger: Zap,
    action: Play,
    condition: GitBranch,
    whatsapp_message: MessageSquare,
    whatsapp_mention: MessageSquare,
    rag_query: Search,
    send_whatsapp_message: Send,
    text_contains: FileText,
    delay: Clock,
    http_request: Globe,
};

export default function CustomNode({ data, selected }: NodeProps) {
    if (!data) return null;
    const Icon = ICONS[data.subType] || ICONS[data.type] || Zap;

    return (
        <div
            className={cn(
                "px-4 py-3 shadow-md rounded-xl border-2 bg-white min-w-[200px] transition-all",
                selected ? "border-primary ring-2 ring-primary/20" : "border-gray-200",
                data.type === "trigger" && "border-l-4 border-l-purple-500",
                data.type === "condition" && "border-l-4 border-l-blue-500",
                data.type === "action" && "border-l-4 border-l-green-500"
            )}
        >
            <div className="flex items-center gap-3">
                <div className={cn(
                    "h-8 w-8 rounded-lg flex items-center justify-center text-white",
                    data.type === "trigger" && "bg-purple-500",
                    data.type === "condition" && "bg-blue-500",
                    data.type === "action" && "bg-green-500"
                )}>
                    <Icon className="h-4 w-4" />
                </div>
                <div>
                    <div className="text-sm font-bold text-gray-900">{data.label || 'Unnamed Node'}</div>
                    <div className="text-xs text-gray-500 capitalize">{data.subType?.replace(/_/g, " ") || data.type || 'Custom'}</div>
                </div>
            </div>

            <Handle
                type="target"
                position={Position.Top}
                className={cn(
                    "w-3 h-3 border-2 bg-white",
                    data.type === "trigger" ? "invisible" : ""
                )}
            />

            {data.type === "condition" ? (
                <>
                    <div className="absolute -bottom-3 left-1/4 transform -translate-x-1/2 flex flex-col items-center">
                        <span className="text-[10px] font-bold text-green-600 bg-white px-1 shadow-sm rounded mb-1">True</span>
                        <Handle
                            type="source"
                            position={Position.Bottom}
                            id="true"
                            className="w-3 h-3 border-2 bg-green-500"
                            style={{ left: '25%' }}
                        />
                    </div>
                    <div className="absolute -bottom-3 right-1/4 transform translate-x-1/2 flex flex-col items-center">
                        <span className="text-[10px] font-bold text-red-600 bg-white px-1 shadow-sm rounded mb-1">False</span>
                        <Handle
                            type="source"
                            position={Position.Bottom}
                            id="false"
                            className="w-3 h-3 border-2 bg-red-500"
                            style={{ left: '75%' }}
                        />
                    </div>
                </>
            ) : (
                <Handle
                    type="source"
                    position={Position.Bottom}
                    className="w-3 h-3 border-2 bg-white"
                />
            )}
        </div>
    );
}
