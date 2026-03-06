import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from "react";
import ReactFlow, {
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type OnEdgesChange,
  type OnNodesChange,
  type ReactFlowInstance,
  Controls,
  Background,
  MarkerType,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";
import CustomNode from "./CustomNode";
import { DEFAULT_NODES, type FlowNodeData, type NodeType } from "../lib/flowSchema";
import { buildQuickFlowTemplateGraph } from "../lib/flowTemplates";

const nodeTypes = {
  trigger: CustomNode,
  action: CustomNode,
  condition: CustomNode,
};

interface FlowCanvasProps {
  onNodeSelect: (node: Node<FlowNodeData> | null) => void;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  setNodes: Dispatch<SetStateAction<Node<FlowNodeData>[]>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
}

export default function FlowCanvas({
  onNodeSelect,
  nodes,
  edges,
  setNodes,
  setEdges,
  onNodesChange,
  onEdgesChange,
}: FlowCanvasProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null);

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((eds: Edge[]) =>
        addEdge(
          {
            ...params,
            type: "smoothstep",
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { strokeWidth: 1.8, stroke: "#0f766e" },
          },
          eds
        )
      ),
    [setEdges]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!reactFlowInstance) return;

      const flowTemplateId = event.dataTransfer.getData("application/flow-template");
      if (flowTemplateId) {
        const position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY });
        const graph = buildQuickFlowTemplateGraph(flowTemplateId, position);
        if (!graph) return;

        setNodes((nds) => nds.concat(graph.nodes));
        setEdges((eds) => eds.concat(graph.edges));
        return;
      }

      const type = event.dataTransfer.getData("application/reactflow") as NodeType;
      const subType = event.dataTransfer.getData("application/subtype");
      if (!type) return;

      const position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const defaultData = DEFAULT_NODES[subType] || { label: "Node", type, config: {} };

      const newNode: Node<FlowNodeData> = {
        id: `${subType}_${Date.now()}`,
        type,
        position,
        data: {
          ...defaultData,
          type,
          subType,
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes]
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
        onNodeClick={(_, node) => onNodeSelect(node as Node<FlowNodeData>)}
        onPaneClick={() => onNodeSelect(null)}
        nodeTypes={nodeTypes}
        fitView
        defaultViewport={{ x: 0, y: 0, zoom: 0.9 }}
      >
        <Controls className="!border !border-border !bg-white !shadow-sm" />
        <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#d4dce0" />
      </ReactFlow>
    </div>
  );
}
