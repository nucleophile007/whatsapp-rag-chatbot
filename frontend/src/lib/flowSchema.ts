export type NodeType = "trigger" | "action" | "condition";

export interface FlowNodeData {
    label: string;
    type: NodeType;
    config: Record<string, any>;
    [key: string]: any;
}

export const NODE_TYPES = {
    TRIGGER: {
        WHATSAPP_MESSAGE: "whatsapp_message",
        WHATSAPP_MENTION: "whatsapp_mention",
        SCHEDULE: "schedule",
    },
    CONDITION: {
        TEXT_CONTAINS: "text_contains",
        TEXT_NOT_EMPTY: "text_not_empty",
    },
    ACTION: {
        RAG_QUERY: "rag_query",
        SEND_MESSAGE: "send_whatsapp_message",
        DELAY: "delay",
        HTTP_REQUEST: "http_request",
    },
} as const;

export const DEFAULT_NODES = {
    [NODE_TYPES.TRIGGER.WHATSAPP_MENTION]: {
        label: "On Mention",
        type: "trigger",
        config: { bot_lid: "" },
    },
    [NODE_TYPES.ACTION.RAG_QUERY]: {
        label: "RAG Query",
        type: "action",
        config: { query: "{{trigger.body}}" },
    },
    [NODE_TYPES.ACTION.SEND_MESSAGE]: {
        label: "Send Message",
        type: "action",
        config: { chat_id: "{{trigger.chatId}}", text: "" },
    },
    [NODE_TYPES.ACTION.DELAY]: {
        label: "Delay",
        type: "action",
        config: { seconds: "5" },
    },
    [NODE_TYPES.ACTION.HTTP_REQUEST]: {
        label: "HTTP Request",
        type: "action",
        config: {
            url: "https://api.example.com",
            method: "GET",
            headers: "{}",
            body: "{}"
        },
    },
    [NODE_TYPES.CONDITION.TEXT_CONTAINS]: {
        label: "Text Contains",
        type: "condition",
        config: { pattern: "", case_sensitive: false },
    },
};
