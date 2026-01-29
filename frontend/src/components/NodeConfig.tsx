import { type Node } from "reactflow";
import { type FlowNodeData } from "../lib/flowSchema";

interface NodeConfigProps {
    selectedNode: Node<FlowNodeData> | null;
    onUpdate: (id: string, data: Partial<FlowNodeData>) => void;
}

export default function NodeConfig({ selectedNode, onUpdate }: NodeConfigProps) {
    if (!selectedNode) {
        return (
            <div className="w-80 border-l bg-white p-6 flex flex-col items-center justify-center text-center">
                <p className="text-muted-foreground">Select a node to configure</p>
            </div>
        );
    }

    const { data } = selectedNode;

    const handleChange = (key: string, value: any) => {
        onUpdate(selectedNode.id, {
            ...data,
            config: {
                ...data.config,
                [key]: value,
            },
        });
    };

    return (
        <div className="w-80 border-l bg-white p-6 overflow-y-auto">
            <div className="mb-6 pb-4 border-b">
                <h3 className="font-bold text-lg">{data.label}</h3>
                <p className="text-sm text-muted-foreground capitalize">
                    {data.subType?.replace(/_/g, " ")}
                </p>
            </div>

            <div className="space-y-6">
                {Object.entries(data.config || {}).map(([key, value]) => (
                    <div key={key} className="space-y-2">
                        <label className="text-sm font-medium text-gray-700 capitalize">
                            {key.replace(/_/g, " ")}
                        </label>
                        {typeof value === "boolean" ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={value}
                                    onChange={(e) => handleChange(key, e.target.checked)}
                                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                                />
                                <span className="text-sm text-gray-600">Enabled</span>
                            </div>
                        ) : key === "bot_lid" ? (
                            <input
                                type="text"
                                value={value}
                                onChange={(e) => handleChange(key, e.target.value)}
                                placeholder="e.g. 35077249618150"
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            />
                        ) : key === "input" || key === "pattern" || key === "query" || key === "text" || key === "headers" || key === "body" ? (
                            <textarea
                                value={value}
                                onChange={(e) => handleChange(key, e.target.value)}
                                placeholder={`Enter ${key}...`}
                                rows={key === "body" || key === "headers" ? 5 : 3}
                                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            />
                        ) : (
                            <input
                                type="text"
                                value={value}
                                onChange={(e) => handleChange(key, e.target.value)}
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            />
                        )}
                        {/* Helper text for templates */}
                        {(key === "input" || key === "query" || key === "text" || key === "reply_to" || key === "chat_id") && (
                            <p className="text-xs text-muted-foreground">
                                Supports <code>{"{{trigger.body}}"}</code> variables
                            </p>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
