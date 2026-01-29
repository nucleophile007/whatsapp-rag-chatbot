import { useCallback, useRef, useState } from 'react';
import ReactFlow, {
    addEdge,
    type Connection,
    type Edge,
    type Node,
    Controls,
    Background,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import { DEFAULT_NODES, type FlowNodeData } from '../lib/flowSchema';

const nodeTypes = {
    trigger: CustomNode,
    action: CustomNode,
    condition: CustomNode,
};

const edgeTypes = {};

interface FlowCanvasProps {
    onNodeSelect: (node: Node<FlowNodeData> | null) => void;
    nodes: Node<FlowNodeData>[];
    edges: Edge[];
    setNodes: any;
    setEdges: any;
    onNodesChange: any;
    onEdgesChange: any;
}

export default function FlowCanvas({
    onNodeSelect,
    nodes,
    edges,
    setNodes,
    setEdges,
    onNodesChange,
    onEdgesChange
}: FlowCanvasProps) {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);

    const onConnect = useCallback(
        (params: Connection) => setEdges((eds: Edge[]) => addEdge({
            ...params,
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed }
        }, eds)),
        [setEdges],
    );

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault();

            const type = event.dataTransfer.getData('application/reactflow');
            const subType = event.dataTransfer.getData('application/subtype');

            if (typeof type === 'undefined' || !type) {
                return;
            }

            const position = reactFlowInstance.screenToFlowPosition({
                x: event.clientX,
                y: event.clientY,
            });

            const defaultData = (DEFAULT_NODES as any)[subType] || { label: 'Node', config: {} };


            const newNode: Node<FlowNodeData> = {
                id: `${subType}_${Date.now()}`,
                type: type, // 'trigger', 'action', etc.
                position,
                data: {
                    ...defaultData,
                    type: type as any,
                    subType: subType
                },
            };

            setNodes((nds: Node[]) => nds.concat(newNode));
        },
        [reactFlowInstance, setNodes],
    );

    return (
        <div className="flex-1 h-full" ref={reactFlowWrapper}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onInit={setReactFlowInstance}
                onDrop={onDrop}
                onDragOver={onDragOver}
                onNodeClick={(_, node) => onNodeSelect(node)}
                onPaneClick={() => onNodeSelect(null)}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
            >
                <Controls />
                <Background />
            </ReactFlow>
        </div>
    );
}
