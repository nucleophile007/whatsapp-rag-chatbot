import { useState, useEffect, useMemo, useCallback, useRef, type MouseEvent as ReactMouseEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useNodesState, useEdgesState, type Node } from "reactflow";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { getFlow, updateFlow, testFlow } from "../lib/api";
import NodePalette from "../components/NodePalette";
import FlowCanvas from "../components/FlowCanvas";
import NodeConfig from "../components/NodeConfig";
import TemplateVariableExplorer from "../components/TemplateVariableExplorer";
import { Save, ChevronLeft, Loader2, Play, Workflow } from "lucide-react";
import type { FlowUpdateInput } from "../lib/types";
import type { FlowNodeData } from "../lib/flowSchema";

const PANEL_LIMITS = {
  canvasMin: 420,
  paletteMin: 240,
  paletteMax: 560,
  configMin: 280,
  configMax: 640,
  templateMin: 320,
  templateMax: 720,
} as const;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const readPanelWidth = (key: string, fallback: number) => {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
};

function ResizeHandle({ onMouseDown }: { onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void }) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
      onMouseDown={onMouseDown}
      className="group relative z-20 w-2 shrink-0 cursor-col-resize bg-transparent"
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border/70 transition-colors group-hover:bg-primary/60 group-active:bg-primary" />
    </div>
  );
}

export default function FlowBuilder() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const layoutRef = useRef<HTMLElement | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node<FlowNodeData> | null>(null);
  const [activeConfigField, setActiveConfigField] = useState<string | null>(null);
  const [flowName, setFlowName] = useState("");
  const [paletteWidth, setPaletteWidth] = useState(() => readPanelWidth("flowbuilder.palette.width", 300));
  const [configWidth, setConfigWidth] = useState(() => readPanelWidth("flowbuilder.config.width", 360));
  const [templateWidth, setTemplateWidth] = useState(() => readPanelWidth("flowbuilder.template.width", 420));

  const { data: flow, isLoading } = useQuery({
    queryKey: ["flow", id],
    queryFn: () => getFlow(id!),
    enabled: !!id,
  });

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (flow) {
      setFlowName(flow.name || "");
      setNodes(flow.definition?.nodes || []);
      setEdges(flow.definition?.edges || []);
    }
  }, [flow, setNodes, setEdges]);

  useEffect(() => {
    if (!selectedNode) return;
    const latestNode = nodes.find((node) => node.id === selectedNode.id) || null;
    if (!latestNode) {
      setSelectedNode(null);
      setActiveConfigField(null);
      return;
    }
    if (latestNode !== selectedNode) {
      setSelectedNode(latestNode);
    }
  }, [nodes, selectedNode]);

  useEffect(() => {
    setActiveConfigField(null);
  }, [selectedNode?.id]);

  useEffect(() => {
    try {
      window.localStorage.setItem("flowbuilder.palette.width", String(paletteWidth));
    } catch {
      // noop
    }
  }, [paletteWidth]);

  useEffect(() => {
    try {
      window.localStorage.setItem("flowbuilder.config.width", String(configWidth));
    } catch {
      // noop
    }
  }, [configWidth]);

  useEffect(() => {
    try {
      window.localStorage.setItem("flowbuilder.template.width", String(templateWidth));
    } catch {
      // noop
    }
  }, [templateWidth]);

  const isDirty = useMemo(() => {
    if (!flow) return false;
    const current = JSON.stringify({ name: flowName, nodes, edges });
    const initial = JSON.stringify({
      name: flow.name || "",
      nodes: flow.definition?.nodes || [],
      edges: flow.definition?.edges || [],
    });
    return current !== initial;
  }, [flow, flowName, nodes, edges]);

  const saveMutation = useMutation({
    mutationFn: (config: FlowUpdateInput) => updateFlow({ id: id!, data: config }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flow", id] });
      queryClient.invalidateQueries({ queryKey: ["flows"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testFlow(id!),
    onSuccess: (result) => {
      alert(`Test triggered\nStatus: ${result.flow_status}\nNodes: ${result.nodes?.length || 0}`);
    },
    onError: (error: unknown) => {
      const message = error instanceof AxiosError ? error.message : "Unknown error";
      alert(`Test failed: ${message}`);
    },
  });

  const handleSave = useCallback(() => {
    if (!flow) return;
    const resolvedName = flowName.trim() || flow.name;
    saveMutation.mutate({
      name: resolvedName,
      description: flow.description,
      trigger_type: flow.trigger_type,
      trigger_config: flow.trigger_config,
      is_enabled: flow.is_enabled,
      definition: { nodes, edges },
    });
  }, [flow, flowName, nodes, edges, saveMutation]);

  const handleTest = async () => {
    if (!flow || !id) return;
    const resolvedName = flowName.trim() || flow.name;
    await updateFlow({
      id,
      data: {
        name: resolvedName,
        description: flow.description,
        trigger_type: flow.trigger_type,
        trigger_config: flow.trigger_config,
        is_enabled: flow.is_enabled,
        definition: { nodes, edges },
      },
    });
    testMutation.mutate();
  };

  const handleInsertTemplate = useCallback(
    async (template: string) => {
      if (!selectedNode || !activeConfigField) {
        await navigator.clipboard.writeText(template);
        return;
      }

      setNodes((currentNodes) =>
        currentNodes.map((node) => {
          if (node.id !== selectedNode.id) return node;

          const currentValue = node.data?.config?.[activeConfigField];
          if (typeof currentValue === "boolean") {
            return node;
          }

          const currentText = String(currentValue ?? "");
          const delimiter = currentText.trim().length > 0 && !currentText.endsWith(" ") ? " " : "";
          const nextValue = `${currentText}${delimiter}${template}`.trim();

          return {
            ...node,
            data: {
              ...node.data,
              config: {
                ...node.data.config,
                [activeConfigField]: nextValue,
              },
            },
          };
        })
      );
    },
    [activeConfigField, selectedNode, setNodes]
  );

  const startResize = useCallback(
    (target: "palette" | "config" | "template") => (event: ReactMouseEvent<HTMLDivElement>) => {
      event.preventDefault();

      const startX = event.clientX;
      const startPalette = paletteWidth;
      const startConfig = configWidth;
      const startTemplate = templateWidth;
      const hasConfigPanel = Boolean(selectedNode);

      const onMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const containerWidth = layoutRef.current?.clientWidth ?? window.innerWidth;
        const handlesWidth = hasConfigPanel ? 6 : 4;

        if (target === "palette") {
          const maxByLayout =
            containerWidth - startTemplate - (hasConfigPanel ? startConfig : 0) - PANEL_LIMITS.canvasMin - handlesWidth;
          const nextWidth = clamp(
            startPalette + deltaX,
            PANEL_LIMITS.paletteMin,
            Math.max(PANEL_LIMITS.paletteMin, Math.min(PANEL_LIMITS.paletteMax, maxByLayout))
          );
          setPaletteWidth(nextWidth);
          return;
        }

        if (target === "config" && hasConfigPanel) {
          const maxByLayout =
            containerWidth - startPalette - startTemplate - PANEL_LIMITS.canvasMin - handlesWidth;
          const nextWidth = clamp(
            startConfig - deltaX,
            PANEL_LIMITS.configMin,
            Math.max(PANEL_LIMITS.configMin, Math.min(PANEL_LIMITS.configMax, maxByLayout))
          );
          setConfigWidth(nextWidth);
          return;
        }

        const maxByLayout =
          containerWidth - startPalette - (hasConfigPanel ? startConfig : 0) - PANEL_LIMITS.canvasMin - handlesWidth;
        const nextWidth = clamp(
          startTemplate - deltaX,
          PANEL_LIMITS.templateMin,
          Math.max(PANEL_LIMITS.templateMin, Math.min(PANEL_LIMITS.templateMax, maxByLayout))
        );
        setTemplateWidth(nextWidth);
      };

      const onUp = () => {
        document.body.style.removeProperty("cursor");
        document.body.style.removeProperty("user-select");
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [paletteWidth, configWidth, templateWidth, selectedNode]
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isSaveShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s";
      if (!isSaveShortcut) return;
      event.preventDefault();
      handleSave();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleSave]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col p-4 md:p-6">
      <section className="panel mb-4 flex shrink-0 flex-wrap items-center justify-between gap-4 p-4 md:p-5">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="btn-secondary px-3 py-2 text-xs">
            <ChevronLeft className="h-3.5 w-3.5" />
            Back
          </button>

          <div>
            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">
              <Workflow className="h-3.5 w-3.5" />
              Flow Builder
            </div>
            <input
              value={flowName}
              onChange={(event) => setFlowName(event.target.value)}
              className="input-base mt-1 h-10 max-w-md text-base font-bold md:text-lg"
              placeholder="Logic layer name"
            />
            <p className="text-xs text-muted-foreground">
              Trigger: {flow?.trigger_type} {isDirty ? "• Unsaved changes" : "• Saved"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={handleSave} disabled={saveMutation.isPending} className="btn-primary">
            {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </button>
          <button
            onClick={handleTest}
            disabled={testMutation.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {testMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Test
          </button>
        </div>
      </section>

      <section ref={layoutRef} className="panel soft-grid min-h-0 flex flex-1 overflow-hidden">
        <NodePalette width={paletteWidth} />
        <ResizeHandle onMouseDown={startResize("palette")} />
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
          <>
            <ResizeHandle onMouseDown={startResize("config")} />
            <NodeConfig
              width={configWidth}
              selectedNode={selectedNode}
              onFieldFocus={setActiveConfigField}
              onUpdate={(nodeId, data) => {
                setNodes((nds) => nds.map((node) => (node.id === nodeId ? { ...node, data: { ...node.data, ...data } } : node)));
              }}
            />
          </>
        )}
        <ResizeHandle onMouseDown={startResize("template")} />
        <TemplateVariableExplorer
          width={templateWidth}
          flowId={id}
          targetField={activeConfigField}
          onInsertTemplate={handleInsertTemplate}
        />
      </section>
    </div>
  );
}
