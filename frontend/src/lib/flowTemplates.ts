import { MarkerType, type Edge, type Node } from "reactflow";
import { DEFAULT_NODES, type FlowNodeData, type NodeType } from "./flowSchema";

type TemplateNodeDef = {
  id: string;
  type: NodeType;
  subType: string;
  offset: { x: number; y: number };
  config?: Record<string, string | number | boolean>;
};

type TemplateEdgeDef = {
  source: string;
  target: string;
  sourceHandle?: string;
};

export type QuickFlowTemplate = {
  id: string;
  label: string;
  description: string;
  nodes: TemplateNodeDef[];
  edges: TemplateEdgeDef[];
};

export const QUICK_FLOW_TEMPLATES: QuickFlowTemplate[] = [
  {
    id: "mention_rag_reply",
    label: "Mention -> RAG -> Reply",
    description: "Respond with RAG output whenever bot is mentioned.",
    nodes: [
      { id: "trigger", type: "trigger", subType: "whatsapp_mention", offset: { x: -320, y: -10 } },
      { id: "rag", type: "action", subType: "rag_query", offset: { x: -60, y: -10 } },
      {
        id: "send",
        type: "action",
        subType: "send_whatsapp_message",
        offset: { x: 220, y: -10 },
        config: {
          message_type: "text",
          text: "{{nodes.__NODE_rag__.rag_result}}",
          reply_to: "{{trigger.id}}",
        },
      },
    ],
    edges: [
      { source: "trigger", target: "rag" },
      { source: "rag", target: "send" },
    ],
  },
  {
    id: "keyword_router",
    label: "Keyword Router",
    description: "If keyword matches, send one message; else send fallback.",
    nodes: [
      { id: "trigger", type: "trigger", subType: "whatsapp_message", offset: { x: -340, y: 10 } },
      {
        id: "cond",
        type: "condition",
        subType: "text_contains",
        offset: { x: -80, y: 10 },
        config: { input: "{{trigger.body}}", pattern: "pricing", case_sensitive: false },
      },
      {
        id: "yes",
        type: "action",
        subType: "send_whatsapp_message",
        offset: { x: 220, y: -110 },
        config: { message_type: "text", text: "Our latest pricing: https://example.com/pricing", reply_to: "{{trigger.id}}" },
      },
      {
        id: "no",
        type: "action",
        subType: "send_whatsapp_message",
        offset: { x: 220, y: 130 },
        config: { message_type: "text", text: "Tell me what you need, and I can help.", reply_to: "{{trigger.id}}" },
      },
    ],
    edges: [
      { source: "trigger", target: "cond" },
      { source: "cond", target: "yes", sourceHandle: "true" },
      { source: "cond", target: "no", sourceHandle: "false" },
    ],
  },
  {
    id: "webhook_bridge",
    label: "Webhook Bridge",
    description: "Forward message to external API and send result summary.",
    nodes: [
      { id: "trigger", type: "trigger", subType: "whatsapp_message", offset: { x: -320, y: -10 } },
      {
        id: "http",
        type: "action",
        subType: "http_request",
        offset: { x: -40, y: -10 },
        config: {
          url: "https://api.example.com/webhook",
          method: "POST",
          headers: "{\"Content-Type\":\"application/json\"}",
          body: "{\"chatId\":\"{{trigger.chatId}}\",\"body\":\"{{trigger.body}}\",\"messageId\":\"{{trigger.id}}\"}",
        },
      },
      {
        id: "send",
        type: "action",
        subType: "send_whatsapp_message",
        offset: { x: 260, y: -10 },
        config: {
          message_type: "text",
          text: "Webhook processed. HTTP status: {{nodes.__NODE_http__.status_code}}",
          reply_to: "{{trigger.id}}",
        },
      },
    ],
    edges: [
      { source: "trigger", target: "http" },
      { source: "http", target: "send" },
    ],
  },
];

const replaceNodeIdPlaceholders = (value: unknown, nodeIdMap: Record<string, string>): unknown => {
  if (typeof value === "string") {
    return value.replace(/__NODE_([a-zA-Z0-9_]+)__/g, (_, key: string) => nodeIdMap[key] || key);
  }
  if (Array.isArray(value)) {
    return value.map((item) => replaceNodeIdPlaceholders(item, nodeIdMap));
  }
  if (value && typeof value === "object") {
    const input = value as Record<string, unknown>;
    return Object.fromEntries(Object.entries(input).map(([k, v]) => [k, replaceNodeIdPlaceholders(v, nodeIdMap)]));
  }
  return value;
};

export const buildQuickFlowTemplateGraph = (
  templateId: string,
  dropPosition: { x: number; y: number }
): { nodes: Node<FlowNodeData>[]; edges: Edge[] } | null => {
  const template = QUICK_FLOW_TEMPLATES.find((item) => item.id === templateId);
  if (!template) return null;

  const prefix = `${template.id}_${Date.now().toString(36)}_${Math.floor(Math.random() * 1000)}`;
  const nodeIdMap = Object.fromEntries(template.nodes.map((node) => [node.id, `${prefix}_${node.id}`]));

  const nodes: Node<FlowNodeData>[] = template.nodes.map((node) => {
    const baseNode = DEFAULT_NODES[node.subType];
    const defaultConfig = (baseNode?.config || {}) as Record<string, string | number | boolean>;
    const mergedConfig = {
      ...defaultConfig,
      ...(node.config || {}),
    };

    const resolvedConfig = replaceNodeIdPlaceholders(mergedConfig, nodeIdMap) as Record<string, string | number | boolean>;

    return {
      id: nodeIdMap[node.id],
      type: node.type,
      position: {
        x: dropPosition.x + node.offset.x,
        y: dropPosition.y + node.offset.y,
      },
      data: {
        ...(baseNode || { label: node.subType, type: node.type, config: {} }),
        type: node.type,
        subType: node.subType,
        config: resolvedConfig,
      },
    };
  });

  const edges: Edge[] = template.edges.map((edge) => ({
    id: `${prefix}_edge_${edge.source}_${edge.target}_${edge.sourceHandle || "default"}`,
    source: nodeIdMap[edge.source],
    target: nodeIdMap[edge.target],
    sourceHandle: edge.sourceHandle,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { strokeWidth: 1.8, stroke: "#0f766e" },
  }));

  return { nodes, edges };
};
