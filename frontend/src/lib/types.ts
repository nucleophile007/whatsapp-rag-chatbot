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

export interface Contact {
  id: string;
  chat_id: string;
  display_name: string | null;
  phone_number: string | null;
  waha_contact_id?: string | null;
  lid?: string | null;
  phone_jid?: string | null;
  source: string;
  is_active: boolean;
  last_seen_at: string | null;
}

export interface ContactsResponse {
  contacts: Contact[];
  total?: number;
}

export interface SyncContactsResponse {
  status: "success";
  synced: number;
  total: number;
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
  retrieval_profile: RetrievalProfile;
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
  chunk_size_used?: number;
  chunk_overlap_used?: number;
  ocr_used?: boolean;
  points_count?: number;
}

export interface UploadJobStartResponse {
  status: "queued" | "running" | "completed" | "failed";
  job_id: string;
  kb_name: string;
  created_at: string;
  updated_at: string;
  phase: string;
  phase_label: string;
  message: string;
  progress_percent: number;
  file_count: number;
  url_count: number;
  chunk_size_used: number;
  chunk_overlap_used: number;
  ocr_used: boolean;
}

export interface UploadJobStatusResponse {
  status: "queued" | "running" | "completed" | "failed";
  job_id: string;
  kb_name: string;
  created_at: string;
  updated_at: string;
  phase: string;
  phase_label: string;
  message: string;
  progress_percent: number;
  file_count: number;
  url_count: number;
  chunk_size_used: number;
  chunk_overlap_used: number;
  ocr_used: boolean;
  result?: UploadDocumentsResponse;
  error?: string | null;
}

export interface MemoryHistoryMessage {
  role: string;
  content: string;
  timestamp?: string | null;
}

export interface MemoryLtmItem {
  memory_key: string;
  memory_text: string;
  memory_category: string;
  confidence: number;
  hit_count: number;
  is_active: boolean;
  source_message?: string | null;
  metadata?: Record<string, unknown>;
  last_seen_at?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface MemorySnapshotResponse {
  status: "success";
  client_id: string;
  workspace_id?: string | null;
  memory_scope?: "client" | "client_workspace";
  effective_client_id?: string;
  history_count: number;
  ltm_count: number;
  summary: string;
  slots: Record<string, unknown>;
  history: MemoryHistoryMessage[];
  context_preview: string;
  ltm_items: MemoryLtmItem[];
  generated_at: string;
}

export interface MemoryLtmUpdateInput {
  memory_key: string;
  memory_text?: string;
  memory_category?: string;
  confidence?: number;
  is_active?: boolean;
}

export interface MemoryLtmMutationResponse {
  status: "success";
  client_id: string;
  workspace_id?: string | null;
  memory_scope?: "client" | "client_workspace";
  item: MemoryLtmItem;
}

export interface RetrievalProfile {
  final_context_k: number | null;
  retrieval_candidates: number | null;
  grounding_threshold: number | null;
  require_citations: boolean | null;
  min_context_chars: number | null;
  query_variants_limit: number | null;
  clarification_enabled: boolean | null;
  clarification_threshold: number | null;
  chunk_size: number | null;
  chunk_overlap: number | null;
  updated_at: string | null;
}

export interface RetrievalProfileUpdateInput {
  final_context_k?: number | null;
  retrieval_candidates?: number | null;
  grounding_threshold?: number | null;
  require_citations?: boolean | null;
  min_context_chars?: number | null;
  query_variants_limit?: number | null;
  clarification_enabled?: boolean | null;
  clarification_threshold?: number | null;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
}

export interface RetrievalProfileResponse {
  status: "success";
  knowledge_base: {
    id: string;
    name: string;
  };
  profile: RetrievalProfile;
  defaults?: {
    chunk_size: number;
    chunk_overlap: number;
  };
}

export interface RagEvalCaseInput {
  question: string;
  expected_contains?: string[];
}

export interface RagTuningOptions {
  grounding_threshold?: number;
  final_context_k?: number;
  retrieval_candidates?: number;
  require_citations?: boolean;
  min_context_chars?: number;
  query_variants_limit?: number;
  clarification_enabled?: boolean;
  clarification_threshold?: number;
}

export interface RagEvalRequestPayload {
  collection_name: string;
  cases: RagEvalCaseInput[];
  conversation_history?: string;
  system_prompt?: string;
  user_prompt_template?: string;
  rag_options?: RagTuningOptions;
}

export interface RagEvalRetrievedChunk {
  rank: number;
  score: number;
  dense_score: number;
  sparse_score: number;
  source: string;
  page: string | number;
}

export interface RagEvalCaseResult {
  index: number;
  question: string;
  answer: string;
  expected_contains: string[];
  expectation_hit: boolean;
  fallback_used: boolean;
  citation_ok: boolean;
  grounding: {
    reason: string;
    score: number;
    margin: number;
    context_chars: number;
    threshold: number;
    passed: boolean;
  };
  latency_ms: number;
  retrieved_chunks: RagEvalRetrievedChunk[];
}

export interface RagEvalResponse {
  status: "success";
  collection_name: string;
  scorecard_id?: string;
  summary: {
    total_cases: number;
    fallback_rate: number;
    citation_ok_rate: number;
    grounding_pass_rate: number;
    expectation_hit_rate: number;
    avg_latency_ms: number;
  };
  results: RagEvalCaseResult[];
  timestamp: string;
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
  contact_filter_mode: "all" | "only" | "except";
  knowledge_base: { id: string; name: string } | null;
  groups: WorkspaceGroupRef[];
  contacts: Contact[];
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
  low_quality_clarification_text: string | null;
  contact_filter_mode: "all" | "only" | "except";
  is_active: boolean;
  groups: WorkspaceGroupRef[];
  contacts: Contact[];
}

export interface WorkspaceRecord {
  id: string;
  name: string;
  knowledge_base_id: string | null;
  system_prompt: string | null;
  user_prompt_template: string | null;
  low_quality_clarification_text: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceFormInput {
  name: string;
  knowledge_base_id: string;
  system_prompt?: string | null;
  user_prompt_template?: string | null;
  low_quality_clarification_text?: string | null;
  contact_filter_mode?: "all" | "only" | "except";
  contact_chat_ids?: string[];
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

export interface ExecutionDeleteResponse {
  status: "success";
  deleted_id: string;
}

export interface ExecutionBulkDeleteResponse {
  status: "success";
  requested_count: number;
  deleted_count: number;
}

export interface ExecutionClearResponse {
  status: "success";
  scope: string;
  deleted_count: number;
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
