import type {
  ApiStatusMessage,
  Contact,
  ContactsResponse,
  Collection,
  CollectionRecord,
  CollectionsResponse,
  DeleteFlowResponse,
  ExecutionBulkDeleteResponse,
  ExecutionClearResponse,
  ExecutionDeleteResponse,
  ExecutionRecord,
  ExecutionsResponse,
  FlowDefinition,
  FlowDetail,
  FlowsResponse,
  FlowMutationResponse,
  FlowSummary,
  FlowTemplate,
  Group,
  GroupsResponse,
  MemoryHistoryMessage,
  MemoryLtmItem,
  MemoryLtmMutationResponse,
  MemorySnapshotResponse,
  SyncCollectionsResponse,
  SyncContactsResponse,
  SyncGroupsResponse,
  TemplatesResponse,
  TestFlowResponse,
  ToggleGroupResponse,
  ToggleWorkspaceResponse,
  UploadDocumentsResponse,
  UploadJobStartResponse,
  UploadJobStatusResponse,
  RagEvalResponse,
  RetrievalProfile,
  RetrievalProfileResponse,
  WorkspaceDetailResponse,
  WorkspaceGroupRef,
  WorkspaceRecord,
  WorkerStatusResponse,
  WorkspacesResponse,
} from "./types";
import type { Edge, Node } from "reactflow";
import type { FlowNodeData } from "./flowSchema";

type UnknownRecord = Record<string, unknown>;

function describeValue(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function validationError(path: string, expected: string, received: unknown): never {
  throw new Error(`API contract mismatch at '${path}': expected ${expected}, received ${describeValue(received)}`);
}

function asRecord(value: unknown, path: string): UnknownRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    validationError(path, "object", value);
  }
  return value as UnknownRecord;
}

function asArray<T>(value: unknown, path: string, mapItem: (item: unknown, index: number) => T): T[] {
  if (!Array.isArray(value)) {
    validationError(path, "array", value);
  }
  return value.map((item, index) => mapItem(item, index));
}

function asString(value: unknown, path: string): string {
  if (typeof value !== "string") {
    validationError(path, "string", value);
  }
  return value;
}

function asStringOrNull(value: unknown, path: string): string | null {
  if (value === null) return null;
  return asString(value, path);
}

function asBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    validationError(path, "boolean", value);
  }
  return value;
}

function asNumber(value: unknown, path: string): number {
  if (typeof value !== "number") {
    validationError(path, "number", value);
  }
  return value;
}

function asObjectOrNull(value: unknown, path: string): UnknownRecord | null {
  if (value === null) return null;
  return asRecord(value, path);
}

function asUnknownRecord(value: unknown, path: string): Record<string, unknown> {
  return asRecord(value, path);
}

function pick(record: UnknownRecord, key: string, path: string): unknown {
  if (!(key in record)) {
    validationError(path, `field '${key}'`, undefined);
  }
  return record[key];
}

function parseAssignedFlowRef(value: unknown, path: string): { id: string; name: string } {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
  };
}

function parseGroup(value: unknown, path: string): Group {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    chat_id: asString(pick(record, "chat_id", path), `${path}.chat_id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    description: asStringOrNull(pick(record, "description", path), `${path}.description`),
    member_count: asNumber(pick(record, "member_count", path), `${path}.member_count`),
    avatar_url: asStringOrNull(pick(record, "avatar_url", path), `${path}.avatar_url`),
    is_enabled: asBoolean(pick(record, "is_enabled", path), `${path}.is_enabled`),
    synced_at: asStringOrNull(pick(record, "synced_at", path), `${path}.synced_at`),
    last_message_at: asStringOrNull(pick(record, "last_message_at", path), `${path}.last_message_at`),
    assigned_flows: asArray(pick(record, "assigned_flows", path), `${path}.assigned_flows`, (item, i) =>
      parseAssignedFlowRef(item, `${path}.assigned_flows[${i}]`)
    ),
  };
}

function parseContact(value: unknown, path: string): Contact {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    chat_id: asString(pick(record, "chat_id", path), `${path}.chat_id`),
    display_name:
      "display_name" in record
        ? asStringOrNull(pick(record, "display_name", path), `${path}.display_name`)
        : null,
    phone_number:
      "phone_number" in record
        ? asStringOrNull(pick(record, "phone_number", path), `${path}.phone_number`)
        : null,
    waha_contact_id:
      "waha_contact_id" in record
        ? asStringOrNull(pick(record, "waha_contact_id", path), `${path}.waha_contact_id`)
        : null,
    lid:
      "lid" in record
        ? asStringOrNull(pick(record, "lid", path), `${path}.lid`)
        : null,
    phone_jid:
      "phone_jid" in record
        ? asStringOrNull(pick(record, "phone_jid", path), `${path}.phone_jid`)
        : null,
    source:
      "source" in record
        ? asString(pick(record, "source", path), `${path}.source`)
        : "webhook",
    is_active:
      "is_active" in record
        ? asBoolean(pick(record, "is_active", path), `${path}.is_active`)
        : true,
    last_seen_at:
      "last_seen_at" in record
        ? asStringOrNull(pick(record, "last_seen_at", path), `${path}.last_seen_at`)
        : null,
  };
}

function parseWorkspaceGroupRef(value: unknown, path: string): WorkspaceGroupRef {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    chat_id: asString(pick(record, "chat_id", path), `${path}.chat_id`),
  };
}

function parseCollection(value: unknown, path: string): Collection {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    description: asStringOrNull(pick(record, "description", path), `${path}.description`),
    created_at: asString(pick(record, "created_at", path), `${path}.created_at`),
    retrieval_profile:
      "retrieval_profile" in record
        ? parseRetrievalProfile(
            pick(record, "retrieval_profile", path),
            `${path}.retrieval_profile`
          )
        : emptyRetrievalProfile(),
  };
}

function parseNumberOrNull(value: unknown, path: string): number | null {
  if (value === null) return null;
  return asNumber(value, path);
}

function parseBooleanOrNull(value: unknown, path: string): boolean | null {
  if (value === null) return null;
  return asBoolean(value, path);
}

function parseRetrievalProfile(value: unknown, path: string): RetrievalProfile {
  const record = asRecord(value, path);
  return {
    final_context_k: parseNumberOrNull(pick(record, "final_context_k", path), `${path}.final_context_k`),
    retrieval_candidates: parseNumberOrNull(
      pick(record, "retrieval_candidates", path),
      `${path}.retrieval_candidates`
    ),
    grounding_threshold: parseNumberOrNull(
      pick(record, "grounding_threshold", path),
      `${path}.grounding_threshold`
    ),
    require_citations: parseBooleanOrNull(
      pick(record, "require_citations", path),
      `${path}.require_citations`
    ),
    min_context_chars: parseNumberOrNull(pick(record, "min_context_chars", path), `${path}.min_context_chars`),
    query_variants_limit: parseNumberOrNull(
      pick(record, "query_variants_limit", path),
      `${path}.query_variants_limit`
    ),
    clarification_enabled: parseBooleanOrNull(
      pick(record, "clarification_enabled", path),
      `${path}.clarification_enabled`
    ),
    clarification_threshold: parseNumberOrNull(
      pick(record, "clarification_threshold", path),
      `${path}.clarification_threshold`
    ),
    chunk_size: parseNumberOrNull(pick(record, "chunk_size", path), `${path}.chunk_size`),
    chunk_overlap: parseNumberOrNull(pick(record, "chunk_overlap", path), `${path}.chunk_overlap`),
    updated_at: asStringOrNull(pick(record, "updated_at", path), `${path}.updated_at`),
  };
}

function emptyRetrievalProfile(): RetrievalProfile {
  return {
    final_context_k: null,
    retrieval_candidates: null,
    grounding_threshold: null,
    require_citations: null,
    min_context_chars: null,
    query_variants_limit: null,
    clarification_enabled: null,
    clarification_threshold: null,
    chunk_size: null,
    chunk_overlap: null,
    updated_at: null,
  };
}

function parseFlowDefinition(value: unknown, path: string): FlowDefinition {
  const record = asRecord(value, path);
  const nodes = asArray(pick(record, "nodes", path), `${path}.nodes`, (item, index) =>
    asRecord(item, `${path}.nodes[${index}]`) as unknown as Node<FlowNodeData>
  );
  const edges = asArray(pick(record, "edges", path), `${path}.edges`, (item, index) =>
    asRecord(item, `${path}.edges[${index}]`) as unknown as Edge
  );
  return { nodes, edges };
}

function parseFlowSummary(value: unknown, path: string): FlowSummary {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    description: asStringOrNull(pick(record, "description", path), `${path}.description`),
    workspace_id: asStringOrNull(pick(record, "workspace_id", path), `${path}.workspace_id`),
    workspace_name: asStringOrNull(pick(record, "workspace_name", path), `${path}.workspace_name`),
    workspace_ids: asArray(pick(record, "workspace_ids", path), `${path}.workspace_ids`, (item, index) =>
      asString(item, `${path}.workspace_ids[${index}]`)
    ),
    workspace_names: asArray(pick(record, "workspace_names", path), `${path}.workspace_names`, (item, index) =>
      asString(item, `${path}.workspace_names[${index}]`)
    ),
    workspace_count: asNumber(pick(record, "workspace_count", path), `${path}.workspace_count`),
    trigger_type: asString(pick(record, "trigger_type", path), `${path}.trigger_type`),
    is_enabled: asBoolean(pick(record, "is_enabled", path), `${path}.is_enabled`),
    created_at: asStringOrNull(pick(record, "created_at", path), `${path}.created_at`),
    updated_at: asStringOrNull(pick(record, "updated_at", path), `${path}.updated_at`),
  };
}

function parseExecutionRecord(value: unknown, path: string): ExecutionRecord {
  const record = asRecord(value, path);
  const nodesExecutedValue = pick(record, "nodes_executed", path);
  if (!(nodesExecutedValue === null || Array.isArray(nodesExecutedValue) || typeof nodesExecutedValue === "string")) {
    validationError(`${path}.nodes_executed`, "array|string|null", nodesExecutedValue);
  }

  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    flow_id: asString(pick(record, "flow_id", path), `${path}.flow_id`),
    status: asString(pick(record, "status", path), `${path}.status`) as ExecutionRecord["status"],
    started_at: asStringOrNull(pick(record, "started_at", path), `${path}.started_at`),
    completed_at: asStringOrNull(pick(record, "completed_at", path), `${path}.completed_at`),
    trigger_data: asUnknownRecord(pick(record, "trigger_data", path), `${path}.trigger_data`),
    nodes_executed: nodesExecutedValue as ExecutionRecord["nodes_executed"],
  };
}

function parseMemoryHistoryMessage(value: unknown, path: string): MemoryHistoryMessage {
  const record = asRecord(value, path);
  return {
    role: asString(pick(record, "role", path), `${path}.role`),
    content: asString(pick(record, "content", path), `${path}.content`),
    timestamp:
      "timestamp" in record
        ? asStringOrNull(pick(record, "timestamp", path), `${path}.timestamp`)
        : null,
  };
}

function parseMemoryLtmItem(value: unknown, path: string): MemoryLtmItem {
  const record = asRecord(value, path);
  return {
    memory_key: asString(pick(record, "memory_key", path), `${path}.memory_key`),
    memory_text: asString(pick(record, "memory_text", path), `${path}.memory_text`),
    memory_category: asString(pick(record, "memory_category", path), `${path}.memory_category`),
    confidence: asNumber(pick(record, "confidence", path), `${path}.confidence`),
    hit_count: asNumber(pick(record, "hit_count", path), `${path}.hit_count`),
    is_active: asBoolean(pick(record, "is_active", path), `${path}.is_active`),
    source_message:
      "source_message" in record
        ? asStringOrNull(pick(record, "source_message", path), `${path}.source_message`)
        : null,
    metadata:
      "metadata" in record
        ? (asObjectOrNull(pick(record, "metadata", path), `${path}.metadata`) || {})
        : {},
    last_seen_at:
      "last_seen_at" in record
        ? asStringOrNull(pick(record, "last_seen_at", path), `${path}.last_seen_at`)
        : null,
    updated_at:
      "updated_at" in record
        ? asStringOrNull(pick(record, "updated_at", path), `${path}.updated_at`)
        : null,
    created_at:
      "created_at" in record
        ? asStringOrNull(pick(record, "created_at", path), `${path}.created_at`)
        : null,
  };
}

export function parseGroupsResponse(value: unknown): GroupsResponse {
  const record = asRecord(value, "groupsResponse");
  return {
    groups: asArray(pick(record, "groups", "groupsResponse"), "groupsResponse.groups", (item, index) =>
      parseGroup(item, `groupsResponse.groups[${index}]`)
    ),
    total: asNumber(pick(record, "total", "groupsResponse"), "groupsResponse.total"),
  };
}

export function parseSyncGroupsResponse(value: unknown): SyncGroupsResponse {
  const record = asRecord(value, "syncGroupsResponse");
  const status = asString(pick(record, "status", "syncGroupsResponse"), "syncGroupsResponse.status");
  if (status === "success") {
    return {
      status,
      synced: asNumber(pick(record, "synced", "syncGroupsResponse"), "syncGroupsResponse.synced"),
      updated: asNumber(pick(record, "updated", "syncGroupsResponse"), "syncGroupsResponse.updated"),
      total: asNumber(pick(record, "total", "syncGroupsResponse"), "syncGroupsResponse.total"),
    };
  }
  return {
    status: "error",
    message: asString(pick(record, "message", "syncGroupsResponse"), "syncGroupsResponse.message"),
  };
}

export function parseContactsResponse(value: unknown): ContactsResponse {
  const record = asRecord(value, "contactsResponse");
  return {
    contacts: asArray(
      pick(record, "contacts", "contactsResponse"),
      "contactsResponse.contacts",
      (item, index) => parseContact(item, `contactsResponse.contacts[${index}]`)
    ),
    total:
      "total" in record
        ? asNumber(pick(record, "total", "contactsResponse"), "contactsResponse.total")
        : undefined,
  };
}

export function parseSyncContactsResponse(value: unknown): SyncContactsResponse {
  const record = asRecord(value, "syncContactsResponse");
  return {
    status: asString(pick(record, "status", "syncContactsResponse"), "syncContactsResponse.status") as "success",
    synced: asNumber(pick(record, "synced", "syncContactsResponse"), "syncContactsResponse.synced"),
    total: asNumber(pick(record, "total", "syncContactsResponse"), "syncContactsResponse.total"),
  };
}

export function parseToggleGroupResponse(value: unknown): ToggleGroupResponse {
  const record = asRecord(value, "toggleGroupResponse");
  return {
    status: asString(pick(record, "status", "toggleGroupResponse"), "toggleGroupResponse.status") as "success",
    group_id: asString(pick(record, "group_id", "toggleGroupResponse"), "toggleGroupResponse.group_id"),
    chat_id: asString(pick(record, "chat_id", "toggleGroupResponse"), "toggleGroupResponse.chat_id"),
    name: asString(pick(record, "name", "toggleGroupResponse"), "toggleGroupResponse.name"),
    is_enabled: asBoolean(pick(record, "is_enabled", "toggleGroupResponse"), "toggleGroupResponse.is_enabled"),
  };
}

export function parseCollectionsResponse(value: unknown): CollectionsResponse {
  const record = asRecord(value, "collectionsResponse");
  return {
    collections: asArray(pick(record, "collections", "collectionsResponse"), "collectionsResponse.collections", (item, index) =>
      parseCollection(item, `collectionsResponse.collections[${index}]`)
    ),
  };
}

export function parseCollectionRecord(value: unknown): CollectionRecord {
  const base = parseCollection(value, "collectionRecord");
  const record = asRecord(value, "collectionRecord");
  return {
    ...base,
    updated_at: asString(pick(record, "updated_at", "collectionRecord"), "collectionRecord.updated_at"),
  };
}

export function parseSyncCollectionsResponse(value: unknown): SyncCollectionsResponse {
  const record = asRecord(value, "syncCollectionsResponse");
  return {
    status: asString(pick(record, "status", "syncCollectionsResponse"), "syncCollectionsResponse.status") as "success",
    added_count: asNumber(pick(record, "added_count", "syncCollectionsResponse"), "syncCollectionsResponse.added_count"),
    total_found: asNumber(pick(record, "total_found", "syncCollectionsResponse"), "syncCollectionsResponse.total_found"),
  };
}

export function parseUploadDocumentsResponse(value: unknown): UploadDocumentsResponse {
  const record = asRecord(value, "uploadDocumentsResponse");
  return {
    status: asString(pick(record, "status", "uploadDocumentsResponse"), "uploadDocumentsResponse.status") as "success",
    message: asString(pick(record, "message", "uploadDocumentsResponse"), "uploadDocumentsResponse.message"),
    file_count: asNumber(pick(record, "file_count", "uploadDocumentsResponse"), "uploadDocumentsResponse.file_count"),
    chunk_count: asNumber(pick(record, "chunk_count", "uploadDocumentsResponse"), "uploadDocumentsResponse.chunk_count"),
    url_count:
      pick(record, "url_count", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(pick(record, "url_count", "uploadDocumentsResponse"), "uploadDocumentsResponse.url_count"),
    pdf_chunk_count:
      pick(record, "pdf_chunk_count", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(
            pick(record, "pdf_chunk_count", "uploadDocumentsResponse"),
            "uploadDocumentsResponse.pdf_chunk_count"
          ),
    url_chunk_count:
      pick(record, "url_chunk_count", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(
            pick(record, "url_chunk_count", "uploadDocumentsResponse"),
            "uploadDocumentsResponse.url_chunk_count"
          ),
    chunk_size_used:
      pick(record, "chunk_size_used", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(
            pick(record, "chunk_size_used", "uploadDocumentsResponse"),
            "uploadDocumentsResponse.chunk_size_used"
          ),
    chunk_overlap_used:
      pick(record, "chunk_overlap_used", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(
            pick(record, "chunk_overlap_used", "uploadDocumentsResponse"),
            "uploadDocumentsResponse.chunk_overlap_used"
          ),
    ocr_used:
      pick(record, "ocr_used", "uploadDocumentsResponse") == null
        ? undefined
        : asBoolean(
            pick(record, "ocr_used", "uploadDocumentsResponse"),
            "uploadDocumentsResponse.ocr_used"
          ),
    points_count:
      pick(record, "points_count", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(pick(record, "points_count", "uploadDocumentsResponse"), "uploadDocumentsResponse.points_count"),
  };
}

function parseUploadJobBase(record: UnknownRecord, path: string) {
  return {
    job_id: asString(pick(record, "job_id", path), `${path}.job_id`),
    kb_name: asString(pick(record, "kb_name", path), `${path}.kb_name`),
    created_at: asString(pick(record, "created_at", path), `${path}.created_at`),
    updated_at: asString(pick(record, "updated_at", path), `${path}.updated_at`),
    phase: asString(pick(record, "phase", path), `${path}.phase`),
    phase_label: asString(pick(record, "phase_label", path), `${path}.phase_label`),
    message: asString(pick(record, "message", path), `${path}.message`),
    progress_percent: asNumber(pick(record, "progress_percent", path), `${path}.progress_percent`),
    file_count: asNumber(pick(record, "file_count", path), `${path}.file_count`),
    url_count: asNumber(pick(record, "url_count", path), `${path}.url_count`),
    chunk_size_used: asNumber(pick(record, "chunk_size_used", path), `${path}.chunk_size_used`),
    chunk_overlap_used: asNumber(pick(record, "chunk_overlap_used", path), `${path}.chunk_overlap_used`),
    ocr_used: asBoolean(pick(record, "ocr_used", path), `${path}.ocr_used`),
  };
}

export function parseUploadJobStartResponse(value: unknown): UploadJobStartResponse {
  const path = "uploadJobStartResponse";
  const record = asRecord(value, path);
  return {
    status: asString(pick(record, "status", path), `${path}.status`) as UploadJobStartResponse["status"],
    ...parseUploadJobBase(record, path),
  };
}

export function parseUploadJobStatusResponse(value: unknown): UploadJobStatusResponse {
  const path = "uploadJobStatusResponse";
  const record = asRecord(value, path);
  return {
    status: asString(pick(record, "status", path), `${path}.status`) as UploadJobStatusResponse["status"],
    ...parseUploadJobBase(record, path),
    result:
      "result" in record && record.result != null
        ? parseUploadDocumentsResponse(record.result)
        : undefined,
    error:
      "error" in record
        ? record.error == null
          ? null
          : asString(record.error, `${path}.error`)
        : undefined,
  };
}

export function parseMemorySnapshotResponse(value: unknown): MemorySnapshotResponse {
  const record = asRecord(value, "memorySnapshotResponse");
  const workspaceId =
    "workspace_id" in record ? asStringOrNull(record.workspace_id, "memorySnapshotResponse.workspace_id") : null;
  const memoryScope =
    "memory_scope" in record ? asString(record.memory_scope, "memorySnapshotResponse.memory_scope") : "client";
  const effectiveClientId =
    "effective_client_id" in record
      ? asString(record.effective_client_id, "memorySnapshotResponse.effective_client_id")
      : undefined;
  return {
    status: asString(pick(record, "status", "memorySnapshotResponse"), "memorySnapshotResponse.status") as "success",
    client_id: asString(pick(record, "client_id", "memorySnapshotResponse"), "memorySnapshotResponse.client_id"),
    workspace_id: workspaceId,
    memory_scope: memoryScope as "client" | "client_workspace",
    effective_client_id: effectiveClientId,
    history_count: asNumber(pick(record, "history_count", "memorySnapshotResponse"), "memorySnapshotResponse.history_count"),
    ltm_count: asNumber(pick(record, "ltm_count", "memorySnapshotResponse"), "memorySnapshotResponse.ltm_count"),
    summary: asString(pick(record, "summary", "memorySnapshotResponse"), "memorySnapshotResponse.summary"),
    slots: asUnknownRecord(pick(record, "slots", "memorySnapshotResponse"), "memorySnapshotResponse.slots"),
    history: asArray(
      pick(record, "history", "memorySnapshotResponse"),
      "memorySnapshotResponse.history",
      (item, index) => parseMemoryHistoryMessage(item, `memorySnapshotResponse.history[${index}]`)
    ),
    context_preview: asString(
      pick(record, "context_preview", "memorySnapshotResponse"),
      "memorySnapshotResponse.context_preview"
    ),
    ltm_items: asArray(
      pick(record, "ltm_items", "memorySnapshotResponse"),
      "memorySnapshotResponse.ltm_items",
      (item, index) => parseMemoryLtmItem(item, `memorySnapshotResponse.ltm_items[${index}]`)
    ),
    generated_at: asString(pick(record, "generated_at", "memorySnapshotResponse"), "memorySnapshotResponse.generated_at"),
  };
}

export function parseMemoryLtmMutationResponse(value: unknown): MemoryLtmMutationResponse {
  const record = asRecord(value, "memoryLtmMutationResponse");
  const workspaceId =
    "workspace_id" in record ? asStringOrNull(record.workspace_id, "memoryLtmMutationResponse.workspace_id") : null;
  const memoryScope =
    "memory_scope" in record ? asString(record.memory_scope, "memoryLtmMutationResponse.memory_scope") : "client";
  return {
    status: asString(
      pick(record, "status", "memoryLtmMutationResponse"),
      "memoryLtmMutationResponse.status"
    ) as "success",
    client_id: asString(
      pick(record, "client_id", "memoryLtmMutationResponse"),
      "memoryLtmMutationResponse.client_id"
    ),
    workspace_id: workspaceId,
    memory_scope: memoryScope as "client" | "client_workspace",
    item: parseMemoryLtmItem(
      pick(record, "item", "memoryLtmMutationResponse"),
      "memoryLtmMutationResponse.item"
    ),
  };
}

export function parseRetrievalProfileResponse(value: unknown): RetrievalProfileResponse {
  const record = asRecord(value, "retrievalProfileResponse");
  const kb = asRecord(
    pick(record, "knowledge_base", "retrievalProfileResponse"),
    "retrievalProfileResponse.knowledge_base"
  );
  const defaultsRaw =
    "defaults" in record ? asObjectOrNull(record.defaults, "retrievalProfileResponse.defaults") : null;
  return {
    status: asString(pick(record, "status", "retrievalProfileResponse"), "retrievalProfileResponse.status") as "success",
    knowledge_base: {
      id: asString(pick(kb, "id", "retrievalProfileResponse.knowledge_base"), "retrievalProfileResponse.knowledge_base.id"),
      name: asString(
        pick(kb, "name", "retrievalProfileResponse.knowledge_base"),
        "retrievalProfileResponse.knowledge_base.name"
      ),
    },
    profile: parseRetrievalProfile(
      pick(record, "profile", "retrievalProfileResponse"),
      "retrievalProfileResponse.profile"
    ),
    defaults: defaultsRaw
      ? {
          chunk_size: asNumber(
            pick(defaultsRaw, "chunk_size", "retrievalProfileResponse.defaults"),
            "retrievalProfileResponse.defaults.chunk_size"
          ),
          chunk_overlap: asNumber(
            pick(defaultsRaw, "chunk_overlap", "retrievalProfileResponse.defaults"),
            "retrievalProfileResponse.defaults.chunk_overlap"
          ),
        }
      : undefined,
  };
}

export function parseRagEvalResponse(value: unknown): RagEvalResponse {
  const record = asRecord(value, "ragEvalResponse");
  const summary = asRecord(pick(record, "summary", "ragEvalResponse"), "ragEvalResponse.summary");
  const results = asArray(
    pick(record, "results", "ragEvalResponse"),
    "ragEvalResponse.results",
    (item, index) => {
      const row = asRecord(item, `ragEvalResponse.results[${index}]`);
      const grounding = asRecord(
        pick(row, "grounding", `ragEvalResponse.results[${index}]`),
        `ragEvalResponse.results[${index}].grounding`
      );
      return {
        index: asNumber(pick(row, "index", `ragEvalResponse.results[${index}]`), `ragEvalResponse.results[${index}].index`),
        question: asString(
          pick(row, "question", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].question`
        ),
        answer: asString(
          pick(row, "answer", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].answer`
        ),
        expected_contains: asArray(
          pick(row, "expected_contains", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].expected_contains`,
          (token, tokenIndex) => asString(token, `ragEvalResponse.results[${index}].expected_contains[${tokenIndex}]`)
        ),
        expectation_hit: asBoolean(
          pick(row, "expectation_hit", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].expectation_hit`
        ),
        fallback_used: asBoolean(
          pick(row, "fallback_used", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].fallback_used`
        ),
        citation_ok: asBoolean(
          pick(row, "citation_ok", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].citation_ok`
        ),
        grounding: {
          reason: asString(pick(grounding, "reason", `ragEvalResponse.results[${index}].grounding`), `ragEvalResponse.results[${index}].grounding.reason`),
          score: asNumber(pick(grounding, "score", `ragEvalResponse.results[${index}].grounding`), `ragEvalResponse.results[${index}].grounding.score`),
          margin: asNumber(pick(grounding, "margin", `ragEvalResponse.results[${index}].grounding`), `ragEvalResponse.results[${index}].grounding.margin`),
          context_chars: asNumber(
            pick(grounding, "context_chars", `ragEvalResponse.results[${index}].grounding`),
            `ragEvalResponse.results[${index}].grounding.context_chars`
          ),
          threshold: asNumber(
            pick(grounding, "threshold", `ragEvalResponse.results[${index}].grounding`),
            `ragEvalResponse.results[${index}].grounding.threshold`
          ),
          passed: asBoolean(
            pick(grounding, "passed", `ragEvalResponse.results[${index}].grounding`),
            `ragEvalResponse.results[${index}].grounding.passed`
          ),
        },
        latency_ms: asNumber(
          pick(row, "latency_ms", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].latency_ms`
        ),
        retrieved_chunks: asArray(
          pick(row, "retrieved_chunks", `ragEvalResponse.results[${index}]`),
          `ragEvalResponse.results[${index}].retrieved_chunks`,
          (chunk, chunkIndex) => {
            const chunkRow = asRecord(chunk, `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`);
            const rawPage = pick(chunkRow, "page", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`);
            if (!(typeof rawPage === "string" || typeof rawPage === "number")) {
              validationError(
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].page`,
                "string|number",
                rawPage
              );
            }
            return {
              rank: asNumber(
                pick(chunkRow, "rank", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`),
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].rank`
              ),
              score: asNumber(
                pick(chunkRow, "score", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`),
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].score`
              ),
              dense_score: asNumber(
                pick(chunkRow, "dense_score", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`),
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].dense_score`
              ),
              sparse_score: asNumber(
                pick(chunkRow, "sparse_score", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`),
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].sparse_score`
              ),
              source: asString(
                pick(chunkRow, "source", `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}]`),
                `ragEvalResponse.results[${index}].retrieved_chunks[${chunkIndex}].source`
              ),
              page: rawPage,
            };
          }
        ),
      };
    }
  );

  return {
    status: asString(pick(record, "status", "ragEvalResponse"), "ragEvalResponse.status") as "success",
    collection_name: asString(pick(record, "collection_name", "ragEvalResponse"), "ragEvalResponse.collection_name"),
    scorecard_id:
      "scorecard_id" in record
        ? asString(record.scorecard_id, "ragEvalResponse.scorecard_id")
        : undefined,
    summary: {
      total_cases: asNumber(pick(summary, "total_cases", "ragEvalResponse.summary"), "ragEvalResponse.summary.total_cases"),
      fallback_rate: asNumber(pick(summary, "fallback_rate", "ragEvalResponse.summary"), "ragEvalResponse.summary.fallback_rate"),
      citation_ok_rate: asNumber(
        pick(summary, "citation_ok_rate", "ragEvalResponse.summary"),
        "ragEvalResponse.summary.citation_ok_rate"
      ),
      grounding_pass_rate: asNumber(
        pick(summary, "grounding_pass_rate", "ragEvalResponse.summary"),
        "ragEvalResponse.summary.grounding_pass_rate"
      ),
      expectation_hit_rate: asNumber(
        pick(summary, "expectation_hit_rate", "ragEvalResponse.summary"),
        "ragEvalResponse.summary.expectation_hit_rate"
      ),
      avg_latency_ms: asNumber(
        pick(summary, "avg_latency_ms", "ragEvalResponse.summary"),
        "ragEvalResponse.summary.avg_latency_ms"
      ),
    },
    results,
    timestamp: asString(pick(record, "timestamp", "ragEvalResponse"), "ragEvalResponse.timestamp"),
  };
}

export function parseWorkspacesResponse(value: unknown): WorkspacesResponse {
  const record = asRecord(value, "workspacesResponse");
  return {
    workspaces: asArray(pick(record, "workspaces", "workspacesResponse"), "workspacesResponse.workspaces", (item, index) => {
      const ws = asRecord(item, `workspacesResponse.workspaces[${index}]`);
      return {
        id: asString(pick(ws, "id", "workspace"), `workspacesResponse.workspaces[${index}].id`),
        name: asString(pick(ws, "name", "workspace"), `workspacesResponse.workspaces[${index}].name`),
        is_active: asBoolean(pick(ws, "is_active", "workspace"), `workspacesResponse.workspaces[${index}].is_active`),
        contact_filter_mode:
          "contact_filter_mode" in ws
            ? (asString(
                pick(ws, "contact_filter_mode", "workspace"),
                `workspacesResponse.workspaces[${index}].contact_filter_mode`
              ) as "all" | "only" | "except")
            : "all",
        knowledge_base: (() => {
          const kb = asObjectOrNull(pick(ws, "knowledge_base", "workspace"), `workspacesResponse.workspaces[${index}].knowledge_base`);
          if (!kb) return null;
          return {
            id: asString(pick(kb, "id", "knowledge_base"), `workspacesResponse.workspaces[${index}].knowledge_base.id`),
            name: asString(pick(kb, "name", "knowledge_base"), `workspacesResponse.workspaces[${index}].knowledge_base.name`),
          };
        })(),
        groups: asArray(pick(ws, "groups", "workspace"), `workspacesResponse.workspaces[${index}].groups`, (groupItem, groupIndex) =>
          parseWorkspaceGroupRef(groupItem, `workspacesResponse.workspaces[${index}].groups[${groupIndex}]`)
        ),
        contacts:
          "contacts" in ws
            ? asArray(pick(ws, "contacts", "workspace"), `workspacesResponse.workspaces[${index}].contacts`, (contactItem, contactIndex) =>
                parseContact(contactItem, `workspacesResponse.workspaces[${index}].contacts[${contactIndex}]`)
              )
            : [],
      };
    }),
  };
}

export function parseWorkspaceRecord(value: unknown): WorkspaceRecord {
  const record = asRecord(value, "workspaceRecord");
  return {
    id: asString(pick(record, "id", "workspaceRecord"), "workspaceRecord.id"),
    name: asString(pick(record, "name", "workspaceRecord"), "workspaceRecord.name"),
    knowledge_base_id: asStringOrNull(pick(record, "knowledge_base_id", "workspaceRecord"), "workspaceRecord.knowledge_base_id"),
    system_prompt: asStringOrNull(pick(record, "system_prompt", "workspaceRecord"), "workspaceRecord.system_prompt"),
    user_prompt_template: asStringOrNull(pick(record, "user_prompt_template", "workspaceRecord"), "workspaceRecord.user_prompt_template"),
    low_quality_clarification_text: asStringOrNull(
      pick(record, "low_quality_clarification_text", "workspaceRecord"),
      "workspaceRecord.low_quality_clarification_text"
    ),
    is_active: asBoolean(pick(record, "is_active", "workspaceRecord"), "workspaceRecord.is_active"),
    created_at: asString(pick(record, "created_at", "workspaceRecord"), "workspaceRecord.created_at"),
    updated_at: asString(pick(record, "updated_at", "workspaceRecord"), "workspaceRecord.updated_at"),
  };
}

export function parseWorkspaceDetailResponse(value: unknown): WorkspaceDetailResponse {
  const record = asRecord(value, "workspaceDetailResponse");
  return {
    id: asString(pick(record, "id", "workspaceDetailResponse"), "workspaceDetailResponse.id"),
    name: asString(pick(record, "name", "workspaceDetailResponse"), "workspaceDetailResponse.name"),
    knowledge_base_id: asStringOrNull(pick(record, "knowledge_base_id", "workspaceDetailResponse"), "workspaceDetailResponse.knowledge_base_id"),
    system_prompt: asStringOrNull(pick(record, "system_prompt", "workspaceDetailResponse"), "workspaceDetailResponse.system_prompt"),
    user_prompt_template: asStringOrNull(pick(record, "user_prompt_template", "workspaceDetailResponse"), "workspaceDetailResponse.user_prompt_template"),
    low_quality_clarification_text: asStringOrNull(
      pick(record, "low_quality_clarification_text", "workspaceDetailResponse"),
      "workspaceDetailResponse.low_quality_clarification_text"
    ),
    contact_filter_mode:
      "contact_filter_mode" in record
        ? (asString(
            pick(record, "contact_filter_mode", "workspaceDetailResponse"),
            "workspaceDetailResponse.contact_filter_mode"
          ) as "all" | "only" | "except")
        : "all",
    is_active: asBoolean(pick(record, "is_active", "workspaceDetailResponse"), "workspaceDetailResponse.is_active"),
    groups: asArray(pick(record, "groups", "workspaceDetailResponse"), "workspaceDetailResponse.groups", (item, index) =>
      parseWorkspaceGroupRef(item, `workspaceDetailResponse.groups[${index}]`)
    ),
    contacts:
      "contacts" in record
        ? asArray(pick(record, "contacts", "workspaceDetailResponse"), "workspaceDetailResponse.contacts", (item, index) =>
            parseContact(item, `workspaceDetailResponse.contacts[${index}]`)
          )
        : [],
  };
}

export function parseApiStatusMessage(value: unknown): ApiStatusMessage {
  const record = asRecord(value, "apiStatusMessage");
  return {
    status: asString(pick(record, "status", "apiStatusMessage"), "apiStatusMessage.status"),
    message: asString(pick(record, "message", "apiStatusMessage"), "apiStatusMessage.message"),
  };
}

export function parseToggleWorkspaceResponse(value: unknown): ToggleWorkspaceResponse {
  const record = asRecord(value, "toggleWorkspaceResponse");
  return {
    status: asString(pick(record, "status", "toggleWorkspaceResponse"), "toggleWorkspaceResponse.status") as "success",
    workspace_id: asString(pick(record, "workspace_id", "toggleWorkspaceResponse"), "toggleWorkspaceResponse.workspace_id"),
    is_active: asBoolean(pick(record, "is_active", "toggleWorkspaceResponse"), "toggleWorkspaceResponse.is_active"),
  };
}

export function parseFlowsResponse(value: unknown): FlowsResponse {
  const record = asRecord(value, "flowsResponse");
  return {
    flows: asArray(pick(record, "flows", "flowsResponse"), "flowsResponse.flows", (item, index) =>
      parseFlowSummary(item, `flowsResponse.flows[${index}]`)
    ),
    total: asNumber(pick(record, "total", "flowsResponse"), "flowsResponse.total"),
  };
}

export function parseFlowDetail(value: unknown): FlowDetail {
  const record = asRecord(value, "flowDetail");
  const summary = parseFlowSummary(record, "flowDetail");
  return {
    ...summary,
    definition: parseFlowDefinition(pick(record, "definition", "flowDetail"), "flowDetail.definition"),
    trigger_config: asUnknownRecord(pick(record, "trigger_config", "flowDetail"), "flowDetail.trigger_config"),
  };
}

export function parseFlowMutationResponse(value: unknown): FlowMutationResponse {
  const record = asRecord(value, "flowMutationResponse");
  return {
    status: asString(pick(record, "status", "flowMutationResponse"), "flowMutationResponse.status") as "success",
    flow_id: asString(pick(record, "flow_id", "flowMutationResponse"), "flowMutationResponse.flow_id"),
  };
}

export function parseDeleteFlowResponse(value: unknown): DeleteFlowResponse {
  const record = asRecord(value, "deleteFlowResponse");
  return {
    status: asString(pick(record, "status", "deleteFlowResponse"), "deleteFlowResponse.status") as "success",
    deleted_id: asString(pick(record, "deleted_id", "deleteFlowResponse"), "deleteFlowResponse.deleted_id"),
  };
}

export function parseExecutionsResponse(value: unknown): ExecutionsResponse {
  const record = asRecord(value, "executionsResponse");
  return {
    executions: asArray(pick(record, "executions", "executionsResponse"), "executionsResponse.executions", (item, index) =>
      parseExecutionRecord(item, `executionsResponse.executions[${index}]`)
    ),
    total: asNumber(pick(record, "total", "executionsResponse"), "executionsResponse.total"),
    limit: asNumber(pick(record, "limit", "executionsResponse"), "executionsResponse.limit"),
    offset: asNumber(pick(record, "offset", "executionsResponse"), "executionsResponse.offset"),
  };
}

export function parseExecutionDeleteResponse(value: unknown): ExecutionDeleteResponse {
  const record = asRecord(value, "executionDeleteResponse");
  return {
    status: asString(pick(record, "status", "executionDeleteResponse"), "executionDeleteResponse.status") as "success",
    deleted_id: asString(pick(record, "deleted_id", "executionDeleteResponse"), "executionDeleteResponse.deleted_id"),
  };
}

export function parseExecutionBulkDeleteResponse(value: unknown): ExecutionBulkDeleteResponse {
  const record = asRecord(value, "executionBulkDeleteResponse");
  return {
    status: asString(
      pick(record, "status", "executionBulkDeleteResponse"),
      "executionBulkDeleteResponse.status"
    ) as "success",
    requested_count: asNumber(
      pick(record, "requested_count", "executionBulkDeleteResponse"),
      "executionBulkDeleteResponse.requested_count"
    ),
    deleted_count: asNumber(
      pick(record, "deleted_count", "executionBulkDeleteResponse"),
      "executionBulkDeleteResponse.deleted_count"
    ),
  };
}

export function parseExecutionClearResponse(value: unknown): ExecutionClearResponse {
  const record = asRecord(value, "executionClearResponse");
  return {
    status: asString(pick(record, "status", "executionClearResponse"), "executionClearResponse.status") as "success",
    scope: asString(pick(record, "scope", "executionClearResponse"), "executionClearResponse.scope"),
    deleted_count: asNumber(
      pick(record, "deleted_count", "executionClearResponse"),
      "executionClearResponse.deleted_count"
    ),
  };
}

export function parseTestFlowResponse(value: unknown): TestFlowResponse {
  const record = asRecord(value, "testFlowResponse");
  const nodes = pick(record, "nodes", "testFlowResponse");
  if (!(nodes === null || Array.isArray(nodes))) {
    validationError("testFlowResponse.nodes", "array|null", nodes);
  }

  return {
    status: asString(pick(record, "status", "testFlowResponse"), "testFlowResponse.status") as "success",
    execution_id: asString(pick(record, "execution_id", "testFlowResponse"), "testFlowResponse.execution_id"),
    flow_status: asString(pick(record, "flow_status", "testFlowResponse"), "testFlowResponse.flow_status"),
    nodes: nodes as unknown[] | null,
  };
}

function parseFlowTemplate(value: unknown, path: string): FlowTemplate {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    description: asString(pick(record, "description", path), `${path}.description`),
    trigger_type: asString(pick(record, "trigger_type", path), `${path}.trigger_type`),
    definition: {
      nodes: asArray(pick(asRecord(pick(record, "definition", path), `${path}.definition`), "nodes", `${path}.definition`), `${path}.definition.nodes`, (item, index) =>
        asRecord(item, `${path}.definition.nodes[${index}]`)
      ),
      edges: asArray(pick(asRecord(pick(record, "definition", path), `${path}.definition`), "edges", `${path}.definition`), `${path}.definition.edges`, (item, index) =>
        asRecord(item, `${path}.definition.edges[${index}]`)
      ),
    },
  };
}

export function parseTemplatesResponse(value: unknown): TemplatesResponse {
  const record = asRecord(value, "templatesResponse");
  return {
    templates: asArray(pick(record, "templates", "templatesResponse"), "templatesResponse.templates", (item, index) =>
      parseFlowTemplate(item, `templatesResponse.templates[${index}]`)
    ),
    total: asNumber(pick(record, "total", "templatesResponse"), "templatesResponse.total"),
  };
}

export function parseWorkerStatusResponse(value: unknown): WorkerStatusResponse {
  const record = asRecord(value, "workerStatusResponse");
  return {
    status: asString(pick(record, "status", "workerStatusResponse"), "workerStatusResponse.status") as "success",
    desired_count: asNumber(pick(record, "desired_count", "workerStatusResponse"), "workerStatusResponse.desired_count"),
    active_count: asNumber(pick(record, "active_count", "workerStatusResponse"), "workerStatusResponse.active_count"),
    scheduler_count: asNumber(pick(record, "scheduler_count", "workerStatusResponse"), "workerStatusResponse.scheduler_count"),
    queued_count: asNumber(pick(record, "queued_count", "workerStatusResponse"), "workerStatusResponse.queued_count"),
    processing_count: asNumber(pick(record, "processing_count", "workerStatusResponse"), "workerStatusResponse.processing_count"),
    scheduled_count: asNumber(pick(record, "scheduled_count", "workerStatusResponse"), "workerStatusResponse.scheduled_count"),
    deferred_count: asNumber(pick(record, "deferred_count", "workerStatusResponse"), "workerStatusResponse.deferred_count"),
    failed_count: asNumber(pick(record, "failed_count", "workerStatusResponse"), "workerStatusResponse.failed_count"),
    finished_count: asNumber(pick(record, "finished_count", "workerStatusResponse"), "workerStatusResponse.finished_count"),
    default_queue_depth: asNumber(
      pick(record, "default_queue_depth", "workerStatusResponse"),
      "workerStatusResponse.default_queue_depth"
    ),
    workers: asArray(pick(record, "workers", "workerStatusResponse"), "workerStatusResponse.workers", (item, index) => {
      const worker = asRecord(item, `workerStatusResponse.workers[${index}]`);
      return {
        name: asString(pick(worker, "name", "worker"), `workerStatusResponse.workers[${index}].name`),
        state: asString(pick(worker, "state", "worker"), `workerStatusResponse.workers[${index}].state`),
        queues: asArray(
          pick(worker, "queues", "worker"),
          `workerStatusResponse.workers[${index}].queues`,
          (queueName, qIndex) => asString(queueName, `workerStatusResponse.workers[${index}].queues[${qIndex}]`)
        ),
        current_job_id: asString(
          pick(worker, "current_job_id", "worker"),
          `workerStatusResponse.workers[${index}].current_job_id`
        ),
        is_scheduler: asBoolean(
          pick(worker, "is_scheduler", "worker"),
          `workerStatusResponse.workers[${index}].is_scheduler`
        ),
      };
    }),
    manager_heartbeat: (() => {
      const heartbeat = asObjectOrNull(
        pick(record, "manager_heartbeat", "workerStatusResponse"),
        "workerStatusResponse.manager_heartbeat"
      );
      if (!heartbeat) return null;
      return {
        desired_count:
          "desired_count" in heartbeat
            ? asNumber(heartbeat.desired_count, "workerStatusResponse.manager_heartbeat.desired_count")
            : undefined,
        active_processes:
          "active_processes" in heartbeat
            ? asNumber(heartbeat.active_processes, "workerStatusResponse.manager_heartbeat.active_processes")
            : undefined,
        updated_at:
          "updated_at" in heartbeat
            ? asNumber(heartbeat.updated_at, "workerStatusResponse.manager_heartbeat.updated_at")
            : undefined,
        raw: "raw" in heartbeat ? asString(heartbeat.raw, "workerStatusResponse.manager_heartbeat.raw") : undefined,
      };
    })(),
    flow_runtime: (() => {
      const flowRuntime = asRecord(pick(record, "flow_runtime", "workerStatusResponse"), "workerStatusResponse.flow_runtime");
      return {
        window_minutes: asNumber(
          pick(flowRuntime, "window_minutes", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.window_minutes"
        ),
        recent_total: asNumber(
          pick(flowRuntime, "recent_total", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.recent_total"
        ),
        recent_completed: asNumber(
          pick(flowRuntime, "recent_completed", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.recent_completed"
        ),
        recent_failed: asNumber(
          pick(flowRuntime, "recent_failed", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.recent_failed"
        ),
        running_now: asNumber(
          pick(flowRuntime, "running_now", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.running_now"
        ),
        stale_cleaned:
          "stale_cleaned" in flowRuntime
            ? asNumber(
                pick(flowRuntime, "stale_cleaned", "workerStatusResponse.flow_runtime"),
                "workerStatusResponse.flow_runtime.stale_cleaned"
              )
            : 0,
        error: asStringOrNull(
          pick(flowRuntime, "error", "workerStatusResponse.flow_runtime"),
          "workerStatusResponse.flow_runtime.error"
        ),
      };
    })(),
    limits: (() => {
      const limits = asRecord(pick(record, "limits", "workerStatusResponse"), "workerStatusResponse.limits");
      return {
        min: asNumber(pick(limits, "min", "workerStatusResponse.limits"), "workerStatusResponse.limits.min"),
        max: asNumber(pick(limits, "max", "workerStatusResponse.limits"), "workerStatusResponse.limits.max"),
        default: asNumber(pick(limits, "default", "workerStatusResponse.limits"), "workerStatusResponse.limits.default"),
      };
    })(),
  };
}
