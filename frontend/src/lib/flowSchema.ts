export type NodeType = "trigger" | "action" | "condition";
export type NodeConfigValue = string | number | boolean;

export interface FlowNodeData {
  label: string;
  type: NodeType;
  subType?: string;
  config: Record<string, NodeConfigValue>;
  [key: string]: unknown;
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

export const DEFAULT_NODES: Record<string, FlowNodeData> = {
  [NODE_TYPES.TRIGGER.WHATSAPP_MESSAGE]: {
    label: "On Message",
    type: "trigger",
    config: {},
  },
  [NODE_TYPES.TRIGGER.WHATSAPP_MENTION]: {
    label: "On Mention",
    type: "trigger",
    config: {
      mention_match_self_lid: true,
      mention_match_specific_jids: false,
      mention_specific_jids: "",
      mention_match_text_aliases: true,
      mention_text_aliases: "",
    },
  },
  [NODE_TYPES.TRIGGER.SCHEDULE]: {
    label: "On Schedule",
    type: "trigger",
    config: {
      cron: "0 * * * *",
      timezone: "UTC",
    },
  },
  [NODE_TYPES.ACTION.RAG_QUERY]: {
    label: "RAG Query",
    type: "action",
    config: {
      query: "{{trigger.body}}",
      include_conversation_history: true,
      context_limit: "5",
    },
  },
  [NODE_TYPES.ACTION.SEND_MESSAGE]: {
    label: "Send Message",
    type: "action",
    config: {
      message_type: "text",
      chat_id: "{{trigger.chatId}}",
      reply_to: "{{trigger.id}}",
      text: "",
      link_preview: true,
      link_preview_high_quality: false,
      file_url: "",
      file_data: "",
      file_mimetype: "",
      file_filename: "",
      caption: "",
      convert: false,
      as_note: false,
      latitude: "",
      longitude: "",
      title: "",
      poll_name: "",
      poll_options_json: "[\"Option 1\", \"Option 2\"]",
      poll_multiple_answers: false,
      buttons_header: "",
      buttons_body: "",
      buttons_footer: "",
      buttons_json: "[{\"type\":\"reply\",\"text\":\"OK\"}]",
      poll_message_id: "",
      poll_server_id: "",
      votes_json: "[]",
      message_id: "",
      reaction: "+1",
      payload_json: "{}",
    },
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
      body: "{}",
    },
  },
  [NODE_TYPES.CONDITION.TEXT_CONTAINS]: {
    label: "Text Contains",
    type: "condition",
    config: { input: "{{trigger.body}}", pattern: "", case_sensitive: false },
  },
  [NODE_TYPES.CONDITION.TEXT_NOT_EMPTY]: {
    label: "Text Not Empty",
    type: "condition",
    config: { input: "{{trigger.body}}" },
  },
};
