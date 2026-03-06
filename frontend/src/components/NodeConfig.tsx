import { useEffect, useMemo, useState } from "react";
import { type Node } from "reactflow";
import { DEFAULT_NODES, type FlowNodeData } from "../lib/flowSchema";
import { SlidersHorizontal } from "lucide-react";

interface NodeConfigProps {
  selectedNode: Node<FlowNodeData> | null;
  onUpdate: (id: string, data: Partial<FlowNodeData>) => void;
  onFieldFocus?: (fieldKey: string) => void;
  width?: number;
}

const TEMPLATE_KEYS = new Set(["input", "query", "text", "reply_to", "chat_id", "url", "body", "headers", "payload_json"]);
const HIDDEN_CONFIG_KEYS = new Set(["collection_name", "bot_lid"]);
const MESSAGE_TYPE_OPTIONS = [
  { value: "text", label: "Text" },
  { value: "image", label: "Image" },
  { value: "file", label: "File" },
  { value: "voice", label: "Voice" },
  { value: "video", label: "Video" },
  { value: "location", label: "Location" },
  { value: "poll", label: "Poll" },
  { value: "poll_vote", label: "Poll Vote" },
  { value: "reaction", label: "Reaction" },
  { value: "forward", label: "Forward" },
  { value: "buttons", label: "Buttons (Legacy)" },
] as const;
const SEND_FIELDS_BY_TYPE: Record<string, string[]> = {
  text: ["text", "link_preview", "link_preview_high_quality"],
  image: ["file_url", "file_data", "file_mimetype", "file_filename", "caption"],
  file: ["file_url", "file_data", "file_mimetype", "file_filename", "caption"],
  voice: ["file_url", "file_data", "file_mimetype", "file_filename", "convert"],
  video: ["file_url", "file_data", "file_mimetype", "file_filename", "caption", "convert", "as_note"],
  location: ["latitude", "longitude", "title"],
  poll: ["poll_name", "poll_options_json", "poll_multiple_answers"],
  buttons: ["buttons_header", "buttons_body", "buttons_footer", "buttons_json"],
  poll_vote: ["poll_message_id", "poll_server_id", "votes_json"],
  reaction: ["message_id", "reaction"],
  forward: ["message_id"],
};
const TEXTAREA_KEYS = new Set([
  "input",
  "pattern",
  "query",
  "text",
  "headers",
  "body",
  "payload_json",
  "poll_options_json",
  "buttons_json",
  "votes_json",
  "mention_specific_jids",
  "mention_text_aliases",
]);

type PresetDefinition = {
  id: string;
  label: string;
  description: string;
  values: Record<string, string | number | boolean>;
};

const MESSAGE_PRESETS: Record<string, PresetDefinition[]> = {
  text: [
    {
      id: "reply_echo",
      label: "Echo Reply",
      description: "Simple response that mirrors incoming body.",
      values: {
        text: "You said: {{trigger.body}}",
        reply_to: "{{trigger.id}}",
      },
    },
    {
      id: "reply_formal",
      label: "Support Reply",
      description: "Structured support-style response.",
      values: {
        text: "Hi! We received your message: {{trigger.body}}. Our team will respond shortly.",
        reply_to: "{{trigger.id}}",
      },
    },
  ],
  image: [
    {
      id: "image_remote",
      label: "Remote Image URL",
      description: "Send an image from URL with caption.",
      values: {
        file_url: "https://picsum.photos/800/500",
        file_mimetype: "image/jpeg",
        caption: "Generated image for {{trigger.from}}",
      },
    },
  ],
  file: [
    {
      id: "file_remote",
      label: "Remote Document",
      description: "Send a file from URL with filename and caption.",
      values: {
        file_url: "https://example.com/guide.pdf",
        file_mimetype: "application/pdf",
        file_filename: "guide.pdf",
        caption: "Requested guide",
      },
    },
  ],
  voice: [
    {
      id: "voice_remote",
      label: "Voice Note URL",
      description: "Send a remote audio file as voice note.",
      values: {
        file_url: "https://example.com/audio.ogg",
        file_mimetype: "audio/ogg; codecs=opus",
        convert: false,
      },
    },
  ],
  video: [
    {
      id: "video_remote",
      label: "Video URL",
      description: "Send a remote mp4 video with caption.",
      values: {
        file_url: "https://example.com/video.mp4",
        file_mimetype: "video/mp4",
        file_filename: "video.mp4",
        caption: "Requested video",
        convert: false,
        as_note: false,
      },
    },
  ],
  location: [
    {
      id: "location_hq",
      label: "Office Location",
      description: "Share predefined location pin.",
      values: {
        latitude: "37.7749",
        longitude: "-122.4194",
        title: "Main Office",
      },
    },
  ],
  poll: [
    {
      id: "poll_feedback",
      label: "Feedback Poll",
      description: "Quick customer feedback poll.",
      values: {
        poll_name: "How was your experience?",
        poll_options_json: "[\"Excellent\", \"Good\", \"Needs Improvement\"]",
        poll_multiple_answers: false,
      },
    },
  ],
  poll_vote: [
    {
      id: "poll_vote_example",
      label: "Vote Example",
      description: "Template for submitting poll votes.",
      values: {
        poll_message_id: "{{trigger.id}}",
        votes_json: "[\"option_id_1\"]",
      },
    },
  ],
  reaction: [
    {
      id: "reaction_thumbs_up",
      label: "React to Trigger",
      description: "React to current message with thumbs up.",
      values: {
        message_id: "{{trigger.id}}",
        reaction: "+1",
      },
    },
  ],
  forward: [
    {
      id: "forward_trigger",
      label: "Forward Trigger Message",
      description: "Forward current message to another chat.",
      values: {
        message_id: "{{trigger.id}}",
      },
    },
  ],
  buttons: [
    {
      id: "buttons_basic",
      label: "Quick Reply Buttons",
      description: "Create a basic interactive button message.",
      values: {
        buttons_header: "Need help?",
        buttons_body: "Choose one option",
        buttons_footer: "Powered by Logic Layer",
        buttons_json: "[{\"type\":\"reply\",\"text\":\"Talk to human\"},{\"type\":\"reply\",\"text\":\"Show FAQ\"}]",
      },
    },
  ],
};

export default function NodeConfig({ selectedNode, onUpdate, onFieldFocus, width }: NodeConfigProps) {
  const data = selectedNode?.data;
  const defaultConfigForSubtype = useMemo(() => {
    if (!data?.subType) return {};
    return (DEFAULT_NODES[data.subType]?.config || {}) as Record<string, string | number | boolean>;
  }, [data?.subType]);
  const effectiveConfig = useMemo(
    () =>
      ({
        ...defaultConfigForSubtype,
        ...(data?.config || {}),
      }) as Record<string, string | number | boolean>,
    [data?.config, defaultConfigForSubtype]
  );
  const isSendMessageNode = data?.subType === "send_whatsapp_message";
  const selectedMessageType = String(effectiveConfig.message_type ?? "text");
  const activeSendFields = SEND_FIELDS_BY_TYPE[selectedMessageType] || SEND_FIELDS_BY_TYPE.text;
  const availablePresets = useMemo(() => MESSAGE_PRESETS[selectedMessageType] || [], [selectedMessageType]);
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const activePreset = availablePresets.find((preset) => preset.id === selectedPresetId);

  useEffect(() => {
    setSelectedPresetId("");
  }, [selectedNode?.id, selectedMessageType]);

  if (!selectedNode) {
    return (
      <aside className="shrink-0 border-l border-border/70 bg-white/88 p-6 text-center" style={width ? { width } : undefined}>
        <p className="text-sm text-muted-foreground">Select a node to configure</p>
      </aside>
    );
  }

  const handleChange = (key: string, value: string | number | boolean) => {
    if (!data) return;
    onUpdate(selectedNode.id, {
      ...data,
      config: {
        ...data.config,
        [key]: value,
      },
    });
  };

  const renderField = (key: string, value: string | number | boolean | undefined) => {
    if (typeof value === "boolean") {
      return (
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => handleChange(key, e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
          />
          Enabled
        </label>
      );
    }

    if (TEXTAREA_KEYS.has(key)) {
      return (
        <textarea
          value={String(value ?? "")}
          onChange={(e) => handleChange(key, e.target.value)}
          onFocus={() => onFieldFocus?.(key)}
          placeholder={`Enter ${key}...`}
          rows={key === "payload_json" || key === "body" || key === "headers" ? 6 : 3}
          className="input-base min-h-[84px] resize-y"
        />
      );
    }

    return (
      <input
        type="text"
        value={String(value ?? "")}
        onChange={(e) => handleChange(key, e.target.value)}
        onFocus={() => onFieldFocus?.(key)}
        className="input-base"
      />
    );
  };

  const renderFieldBlock = (key: string, value: string | number | boolean | undefined) => (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground capitalize">
        {key.replace(/_/g, " ")}
      </label>
      {renderField(key, value)}
      {TEMPLATE_KEYS.has(key) && (
        <p className="text-xs text-muted-foreground">
          Supports template vars like <code>{"{{trigger.body}}"}</code>
        </p>
      )}
    </div>
  );

  const applyPreset = () => {
    if (!activePreset || !data) return;
    onUpdate(selectedNode.id, {
      ...data,
      config: {
        ...data.config,
        ...activePreset.values,
      },
    });
  };

  return (
    <aside className="shrink-0 border-l border-border/70 bg-white/88 p-5 overflow-y-auto" style={width ? { width } : undefined}>
      <div className="mb-5 rounded-xl border bg-secondary/40 p-3">
        <div className="mb-1 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Node Config
        </div>
        <h3 className="text-lg font-bold">{data?.label}</h3>
        <p className="text-xs capitalize text-muted-foreground">{data?.subType?.replace(/_/g, " ")}</p>
      </div>

      <div className="space-y-4">
        {isSendMessageNode ? (
          <>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Message Type</label>
              <select
                value={selectedMessageType}
                onChange={(e) => handleChange("message_type", e.target.value)}
                className="input-base"
              >
                {MESSAGE_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            {availablePresets.length > 0 && (
              <div className="space-y-2 rounded-xl border border-border/70 bg-secondary/25 p-3">
                <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Payload Preset</label>
                <div className="flex gap-2">
                  <select
                    value={selectedPresetId}
                    onChange={(event) => setSelectedPresetId(event.target.value)}
                    className="input-base"
                  >
                    <option value="">Choose preset...</option>
                    {availablePresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={applyPreset}
                    disabled={!activePreset}
                    className="btn-secondary whitespace-nowrap px-3 py-2 text-xs disabled:opacity-50"
                  >
                    Apply
                  </button>
                </div>
                {activePreset && <p className="text-xs text-muted-foreground">{activePreset.description}</p>}
              </div>
            )}

            {renderFieldBlock("chat_id", effectiveConfig.chat_id)}
            {renderFieldBlock("reply_to", effectiveConfig.reply_to)}
            {activeSendFields.map((key) => (
              <div key={key}>{renderFieldBlock(key, effectiveConfig[key])}</div>
            ))}

            <div className="rounded-xl border border-dashed border-border/70 bg-secondary/30 p-3 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground">Advanced WAHA Payload</p>
              <p className="mt-1">
                Add any WAHA fields in <code>payload_json</code>. These values override basic fields and also support templates.
              </p>
            </div>
            {renderFieldBlock("payload_json", effectiveConfig.payload_json)}
          </>
        ) : (
          Object.entries(effectiveConfig)
            .filter(([key]) => !HIDDEN_CONFIG_KEYS.has(key))
            .map(([key, value]) => <div key={key}>{renderFieldBlock(key, value)}</div>)
        )}
      </div>
    </aside>
  );
}
