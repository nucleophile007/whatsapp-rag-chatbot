import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useNodesState, useEdgesState } from 'reactflow';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getFlow, updateFlow, testFlow } from '../lib/api';
import NodePalette from '../components/NodePalette';
import FlowCanvas from '../components/FlowCanvas';
import NodeConfig from '../components/NodeConfig';
import { Save, ChevronLeft, Loader2, Play } from 'lucide-react';

export default function FlowBuilder() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [selectedNode, setSelectedNode] = useState<any>(null);

    const { data: flow, isLoading } = useQuery({
        queryKey: ['flow', id],
        queryFn: () => getFlow(id!),
        enabled: !!id,
    });

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    useEffect(() => {
        if (flow) {
            setNodes(flow.definition?.nodes || []);
            setEdges(flow.definition?.edges || []);
        }
    }, [flow, setNodes, setEdges]);

    const saveMutation = useMutation({
        mutationFn: (config: any) => updateFlow({ id: id!, data: config }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['flow', id] });
        },
    });

    const testMutation = useMutation({
        mutationFn: () => testFlow(id!),
        onSuccess: (data) => {
            alert(`✅ Test Execution Triggered!\nStatus: ${data.flow_status}\nNodes: ${data.nodes?.length || 0}`);
        },
        onError: (err: any) => {
            alert(`❌ Test Failed: ${err.message}`);
        }
    });

    const handleSave = () => {
        if (!flow) return;
        saveMutation.mutate({
            ...flow,
            definition: { nodes, edges }
        });
    };

    const handleTest = async () => {
        if (!flow) return;
        // Save first ensuring we test latest
        await updateFlow({
            id: id!,
            data: { ...flow, definition: { nodes, edges } }
        });
        testMutation.mutate();
    };

    if (isLoading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin" /></div>;
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <header className="h-16 bg-white border-b flex items-center justify-between px-6 shrink-0">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate(-1)} className="p-2 hover:bg-gray-100 rounded-lg">
                        <ChevronLeft />
                    </button>
                    <div>
                        <h1 className="font-bold text-lg">{flow?.name || 'Automation Flow'}</h1>
                        <p className="text-xs text-gray-400 font-medium">Trigger: {flow?.trigger_type}</p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={handleSave}
                        disabled={saveMutation.isPending}
                        className="bg-primary text-white px-4 py-2 rounded-lg font-bold flex items-center gap-2 hover:bg-primary/90 transition-all shadow-sm"
                    >
                        {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        Save Flow
                    </button>
                    <button
                        onClick={handleTest}
                        disabled={testMutation.isPending}
                        className="bg-green-500 text-white px-4 py-2 rounded-lg font-bold flex items-center gap-2 hover:bg-green-600 transition-all shadow-sm disabled:opacity-50"
                    >
                        {testMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                        Test
                    </button>
                </div>
            </header>

            <div className="flex-1 flex overflow-hidden">
                <NodePalette />
                <FlowCanvas
                    onNodeSelect={setSelectedNode}
                    nodes={nodes}
                    edges={edges}
                    setNodes={setNodes}
                    setEdges={setEdges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                />
                {selectedNode && (
                    <NodeConfig
                        selectedNode={selectedNode}
                        onUpdate={(id, data) => {
                            setNodes((nds) =>
                                nds.map((node) =>
                                    node.id === id ? { ...node, data: { ...node.data, ...data } } : node
                                )
                            );
                        }}
                    />
                )}
            </div>
        </div>
    );
}
