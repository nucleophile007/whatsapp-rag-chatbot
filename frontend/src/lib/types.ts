import type { Edge, Node } from "reactflow";
import type { FlowNodeData } from "./flowSchema";

export interface ApiStatusMessage {
  status: string;
  message: string;
}

export interface ApiErrorDetail {
  detail: string;
}

export interface AssignedFlowRef {
  id: string;
  name: string;
}

export interface Group {
  id: string;
  chat_id: string;
  name: string;
  description: string | null;
  member_count: number;
  avatar_url: string | null;
  is_enabled: boolean;
  synced_at: string | null;
  last_message_at: string | null;
  assigned_flows: AssignedFlowRef[];
}

export interface GroupsResponse {
  groups: Group[];
  total?: number;
}

export interface ToggleGroupResponse {
  status: "success";
  group_id: string;
  chat_id: string;
  name: string;
  is_enabled: boolean;
}

export interface SyncGroupsSuccess {
  status: "success";
  synced: number;
  updated: number;
  total: number;
}

export interface SyncGroupsError {
  status: "error";
  message: string;
}

export type SyncGroupsResponse = SyncGroupsSuccess | SyncGroupsError;

export interface Collection {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface CollectionRecord extends Collection {
  updated_at: string;
}

export interface CollectionsResponse {
  collections: Collection[];
}

export interface SyncCollectionsResponse {
  status: "success";
  added_count: number;
  total_found: number;
}

export interface UploadDocumentsResponse {
  status: "success";
  message: string;
  file_count: number;
  url_count?: number;
  chunk_count: number;
  pdf_chunk_count?: number;
  url_chunk_count?: number;
  points_count?: number;
}

export interface ClientChatRequestPayload {
  message: string;
  client_id?: string;
  collection_name?: string;
  client_system?: string;
  device_fingerprint?: string;
  conversation_limit?: number;
  clear_history?: boolean;
  system_prompt?: string;
  user_prompt_template?: string;
  prompt_technique?: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  temperature?: number;
  max_output_tokens?: number;
}

export interface RateLimitMeta {
  enabled: boolean;
  limit: number;
  used: number;
  remaining: number | null;
  scope: string;
  reset_at?: string;
}

export interface ClientChatResponse {
  status: "success";
  reply: string;
  client_id: string;
  client_id_strategy: string;
  response_mode: "direct" | "rag";
  collection_name: string | null;
  prompt_technique: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  rate_limit: RateLimitMeta;
  model: string;
  timestamp: string;
}

export interface ClientChatDocsResponse {
  status: "success";
  base_url: string;
  endpoint: string;
  stream_endpoint: string;
  method: string;
  active_collection_name: string | null;
  available_collections: string[];
  supported_prompt_techniques: Array<"balanced" | "concise" | "detailed" | "strict_context" | "socratic">;
  auth: {
    header: string;
    required: boolean;
    mode: "open" | "global" | "tenant";
  };
  scope: {
    allow_all_collections: boolean;
    allowed_collections: string[];
    default_collection_name: string | null;
    key_name: string | null;
    daily_limit_per_device: number | null;
    default_prompt_technique: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  };
  curl_example: string;
  javascript_example: string;
  sse_javascript_example: string;
  html_widget_template: string;
}

export interface ClientApiKeyRecord {
  id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  allow_all_collections: boolean;
  allowed_collections: string[];
  default_collection_name: string | null;
  daily_limit_per_device: number | null;
  default_system_prompt: string | null;
  default_user_prompt_template: string | null;
  default_prompt_technique: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  is_active: boolean;
  last_used_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ClientApiKeysResponse {
  status: "success";
  total: number;
  keys: ClientApiKeyRecord[];
}

export interface ClientApiKeyCreateInput {
  name: string;
  description?: string;
  allow_all_collections?: boolean;
  allowed_collections?: string[];
  default_collection_name?: string;
  daily_limit_per_device?: number;
  default_system_prompt?: string;
  default_user_prompt_template?: string;
  default_prompt_technique?: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  is_active?: boolean;
}

export interface ClientApiKeyUpdateInput {
  name?: string;
  description?: string | null;
  allow_all_collections?: boolean;
  allowed_collections?: string[];
  default_collection_name?: string | null;
  daily_limit_per_device?: number;
  default_system_prompt?: string | null;
  default_user_prompt_template?: string | null;
  default_prompt_technique?: "balanced" | "concise" | "detailed" | "strict_context" | "socratic";
  is_active?: boolean;
  rotate_key?: boolean;
}

export interface ClientApiKeyMutationResponse {
  status: "success";
  key: ClientApiKeyRecord;
  api_key?: string;
}

export interface ClientApiKeyDeleteResponse {
  status: "success";
  deleted_id: string;
}

export interface WorkspaceGroupRef {
  id: string;
  name: string;
  chat_id: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  is_active: boolean;
  knowledge_base: { id: string; name: string } | null;
  groups: WorkspaceGroupRef[];
}

export interface WorkspacesResponse {
  workspaces: WorkspaceSummary[];
}

export interface WorkspaceDetailResponse {
  id: string;
  name: string;
  knowledge_base_id: string | null;
  system_prompt: string | null;
  user_prompt_template: string | null;
  is_active: boolean;
  groups: WorkspaceGroupRef[];
}

export interface WorkspaceRecord {
  id: string;
  name: string;
  knowledge_base_id: string | null;
  system_prompt: string | null;
  user_prompt_template: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceFormInput {
  name: string;
  knowledge_base_id: string;
  system_prompt?: string | null;
  user_prompt_template?: string | null;
  group_ids: string[];
}

export interface FlowDefinition {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
}

export interface FlowSummary {
  id: string;
  name: string;
  description: string | null;
  workspace_id: string | null;
  workspace_name: string | null;
  workspace_ids: string[];
  workspace_names: string[];
  workspace_count: number;
  trigger_type: string;
  is_enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface FlowsResponse {
  flows: FlowSummary[];
  total: number;
}

export interface FlowDetail extends FlowSummary {
  definition: FlowDefinition;
  trigger_config: Record<string, unknown>;
}

export interface TemplateDefinition {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface FlowTemplate {
  id: string;
  name: string;
  description: string;
  trigger_type: string;
  definition: TemplateDefinition;
}

export interface TemplatesResponse {
  templates: FlowTemplate[];
  total: number;
}

export interface FlowCreateInput {
  name: string;
  description?: string;
  workspace_id?: string;
  workspace_ids?: string[];
  definition: FlowDefinition;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface FlowUpdateInput {
  name?: string;
  description?: string | null;
  workspace_id?: string | null;
  workspace_ids?: string[];
  definition?: FlowDefinition;
  trigger_type?: string;
  trigger_config?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface FlowMutationResponse {
  status: "success";
  flow_id: string;
}

export interface DeleteFlowResponse {
  status: "success";
  deleted_id: string;
}

export interface ExecutionRecord {
  id: string;
  flow_id: string;
  status: "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  trigger_data: Record<string, unknown>;
  nodes_executed: unknown[] | string | null;
}

export interface ExecutionsResponse {
  executions: ExecutionRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface TestFlowResponse {
  status: "success";
  execution_id: string;
  flow_status: string;
  nodes: unknown[] | null;
}

export interface ToggleWorkspaceResponse {
  status: "success";
  workspace_id: string;
  is_active: boolean;
}

export interface WorkspaceStatusInput {
  id: string;
  is_active: boolean;
}

export interface WorkspaceFlowLinkResponse extends ApiStatusMessage {
  workspace_id: string;
  flow_id: string;
}

export interface WorkerStatusItem {
  name: string;
  state: string;
  queues: string[];
  current_job_id: string;
  is_scheduler: boolean;
}

export interface WorkerManagerHeartbeat {
  desired_count?: number;
  active_processes?: number;
  updated_at?: number;
  raw?: string;
}

export interface WorkerLimits {
  min: number;
  max: number;
  default: number;
}

export interface FlowRuntimeSnapshot {
  window_minutes: number;
  recent_total: number;
  recent_completed: number;
  recent_failed: number;
  running_now: number;
  stale_cleaned: number;
  error: string | null;
}

export interface WorkerStatusResponse {
  status: "success";
  desired_count: number;
  active_count: number;
  scheduler_count: number;
  queued_count: number;
  processing_count: number;
  scheduled_count: number;
  deferred_count: number;
  failed_count: number;
  finished_count: number;
  default_queue_depth: number;
  workers: WorkerStatusItem[];
  manager_heartbeat: WorkerManagerHeartbeat | null;
  flow_runtime: FlowRuntimeSnapshot;
  limits: WorkerLimits;
}

export interface WorkerScaleInput {
  desired_count: number;
}
