import type {
  ApiStatusMessage,
  ClientApiKeyDeleteResponse,
  ClientApiKeyMutationResponse,
  ClientApiKeyRecord,
  ClientApiKeysResponse,
  Collection,
  CollectionRecord,
  CollectionsResponse,
  DeleteFlowResponse,
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
  SyncCollectionsResponse,
  SyncGroupsResponse,
  TemplatesResponse,
  TestFlowResponse,
  ToggleGroupResponse,
  ToggleWorkspaceResponse,
  ClientChatDocsResponse,
  ClientChatResponse,
  UploadDocumentsResponse,
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
    points_count:
      pick(record, "points_count", "uploadDocumentsResponse") == null
        ? undefined
        : asNumber(pick(record, "points_count", "uploadDocumentsResponse"), "uploadDocumentsResponse.points_count"),
  };
}

export function parseClientChatResponse(value: unknown): ClientChatResponse {
  const record = asRecord(value, "clientChatResponse");
  const rateLimitRecord = asRecord(
    pick(record, "rate_limit", "clientChatResponse"),
    "clientChatResponse.rate_limit"
  );
  return {
    status: asString(pick(record, "status", "clientChatResponse"), "clientChatResponse.status") as "success",
    reply: asString(pick(record, "reply", "clientChatResponse"), "clientChatResponse.reply"),
    client_id: asString(pick(record, "client_id", "clientChatResponse"), "clientChatResponse.client_id"),
    client_id_strategy: asString(
      pick(record, "client_id_strategy", "clientChatResponse"),
      "clientChatResponse.client_id_strategy"
    ),
    response_mode: asString(
      pick(record, "response_mode", "clientChatResponse"),
      "clientChatResponse.response_mode"
    ) as "direct" | "rag",
    collection_name: asStringOrNull(
      pick(record, "collection_name", "clientChatResponse"),
      "clientChatResponse.collection_name"
    ),
    prompt_technique: asString(
      pick(record, "prompt_technique", "clientChatResponse"),
      "clientChatResponse.prompt_technique"
    ) as "balanced" | "concise" | "detailed" | "strict_context" | "socratic",
    rate_limit: {
      enabled: asBoolean(
        pick(rateLimitRecord, "enabled", "clientChatResponse.rate_limit"),
        "clientChatResponse.rate_limit.enabled"
      ),
      limit: asNumber(
        pick(rateLimitRecord, "limit", "clientChatResponse.rate_limit"),
        "clientChatResponse.rate_limit.limit"
      ),
      used: asNumber(
        pick(rateLimitRecord, "used", "clientChatResponse.rate_limit"),
        "clientChatResponse.rate_limit.used"
      ),
      remaining:
        pick(rateLimitRecord, "remaining", "clientChatResponse.rate_limit") == null
          ? null
          : asNumber(
              pick(rateLimitRecord, "remaining", "clientChatResponse.rate_limit"),
              "clientChatResponse.rate_limit.remaining"
            ),
      scope: asString(
        pick(rateLimitRecord, "scope", "clientChatResponse.rate_limit"),
        "clientChatResponse.rate_limit.scope"
      ),
      reset_at:
        "reset_at" in rateLimitRecord && rateLimitRecord.reset_at != null
          ? asString(rateLimitRecord.reset_at, "clientChatResponse.rate_limit.reset_at")
          : undefined,
    },
    model: asString(pick(record, "model", "clientChatResponse"), "clientChatResponse.model"),
    timestamp: asString(pick(record, "timestamp", "clientChatResponse"), "clientChatResponse.timestamp"),
  };
}

export function parseClientChatDocsResponse(value: unknown): ClientChatDocsResponse {
  const record = asRecord(value, "clientChatDocsResponse");
  const authRecord = asRecord(pick(record, "auth", "clientChatDocsResponse"), "clientChatDocsResponse.auth");
  const scopeRecord = asRecord(pick(record, "scope", "clientChatDocsResponse"), "clientChatDocsResponse.scope");
  return {
    status: asString(pick(record, "status", "clientChatDocsResponse"), "clientChatDocsResponse.status") as "success",
    base_url: asString(pick(record, "base_url", "clientChatDocsResponse"), "clientChatDocsResponse.base_url"),
    endpoint: asString(pick(record, "endpoint", "clientChatDocsResponse"), "clientChatDocsResponse.endpoint"),
    stream_endpoint: asString(
      pick(record, "stream_endpoint", "clientChatDocsResponse"),
      "clientChatDocsResponse.stream_endpoint"
    ),
    method: asString(pick(record, "method", "clientChatDocsResponse"), "clientChatDocsResponse.method"),
    active_collection_name: asStringOrNull(
      pick(record, "active_collection_name", "clientChatDocsResponse"),
      "clientChatDocsResponse.active_collection_name"
    ),
    available_collections: asArray(
      pick(record, "available_collections", "clientChatDocsResponse"),
      "clientChatDocsResponse.available_collections",
      (item, index) => asString(item, `clientChatDocsResponse.available_collections[${index}]`)
    ),
    supported_prompt_techniques: asArray(
      pick(record, "supported_prompt_techniques", "clientChatDocsResponse"),
      "clientChatDocsResponse.supported_prompt_techniques",
      (item, index) =>
        asString(item, `clientChatDocsResponse.supported_prompt_techniques[${index}]`) as
          | "balanced"
          | "concise"
          | "detailed"
          | "strict_context"
          | "socratic"
    ),
    auth: {
      header: asString(pick(authRecord, "header", "clientChatDocsResponse.auth"), "clientChatDocsResponse.auth.header"),
      required: asBoolean(
        pick(authRecord, "required", "clientChatDocsResponse.auth"),
        "clientChatDocsResponse.auth.required"
      ),
      mode: asString(pick(authRecord, "mode", "clientChatDocsResponse.auth"), "clientChatDocsResponse.auth.mode") as
        | "open"
        | "global"
        | "tenant",
    },
    scope: {
      allow_all_collections: asBoolean(
        pick(scopeRecord, "allow_all_collections", "clientChatDocsResponse.scope"),
        "clientChatDocsResponse.scope.allow_all_collections"
      ),
      allowed_collections: asArray(
        pick(scopeRecord, "allowed_collections", "clientChatDocsResponse.scope"),
        "clientChatDocsResponse.scope.allowed_collections",
        (item, index) => asString(item, `clientChatDocsResponse.scope.allowed_collections[${index}]`)
      ),
      default_collection_name: asStringOrNull(
        pick(scopeRecord, "default_collection_name", "clientChatDocsResponse.scope"),
        "clientChatDocsResponse.scope.default_collection_name"
      ),
      key_name: asStringOrNull(
        pick(scopeRecord, "key_name", "clientChatDocsResponse.scope"),
        "clientChatDocsResponse.scope.key_name"
      ),
      daily_limit_per_device:
        pick(scopeRecord, "daily_limit_per_device", "clientChatDocsResponse.scope") == null
          ? null
          : asNumber(
              pick(scopeRecord, "daily_limit_per_device", "clientChatDocsResponse.scope"),
              "clientChatDocsResponse.scope.daily_limit_per_device"
            ),
      default_prompt_technique: asString(
        pick(scopeRecord, "default_prompt_technique", "clientChatDocsResponse.scope"),
        "clientChatDocsResponse.scope.default_prompt_technique"
      ) as "balanced" | "concise" | "detailed" | "strict_context" | "socratic",
    },
    curl_example: asString(
      pick(record, "curl_example", "clientChatDocsResponse"),
      "clientChatDocsResponse.curl_example"
    ),
    javascript_example: asString(
      pick(record, "javascript_example", "clientChatDocsResponse"),
      "clientChatDocsResponse.javascript_example"
    ),
    sse_javascript_example: asString(
      pick(record, "sse_javascript_example", "clientChatDocsResponse"),
      "clientChatDocsResponse.sse_javascript_example"
    ),
    html_widget_template: asString(
      pick(record, "html_widget_template", "clientChatDocsResponse"),
      "clientChatDocsResponse.html_widget_template"
    ),
  };
}

function parseClientApiKeyRecord(value: unknown, path: string): ClientApiKeyRecord {
  const record = asRecord(value, path);
  return {
    id: asString(pick(record, "id", path), `${path}.id`),
    name: asString(pick(record, "name", path), `${path}.name`),
    description: asStringOrNull(pick(record, "description", path), `${path}.description`),
    key_prefix: asString(pick(record, "key_prefix", path), `${path}.key_prefix`),
    allow_all_collections: asBoolean(
      pick(record, "allow_all_collections", path),
      `${path}.allow_all_collections`
    ),
    allowed_collections: asArray(
      pick(record, "allowed_collections", path),
      `${path}.allowed_collections`,
      (item, index) => asString(item, `${path}.allowed_collections[${index}]`)
    ),
    default_collection_name: asStringOrNull(
      pick(record, "default_collection_name", path),
      `${path}.default_collection_name`
    ),
    daily_limit_per_device:
      pick(record, "daily_limit_per_device", path) == null
        ? null
        : asNumber(pick(record, "daily_limit_per_device", path), `${path}.daily_limit_per_device`),
    default_system_prompt: asStringOrNull(pick(record, "default_system_prompt", path), `${path}.default_system_prompt`),
    default_user_prompt_template: asStringOrNull(
      pick(record, "default_user_prompt_template", path),
      `${path}.default_user_prompt_template`
    ),
    default_prompt_technique: asString(
      pick(record, "default_prompt_technique", path),
      `${path}.default_prompt_technique`
    ) as "balanced" | "concise" | "detailed" | "strict_context" | "socratic",
    is_active: asBoolean(pick(record, "is_active", path), `${path}.is_active`),
    last_used_at: asStringOrNull(pick(record, "last_used_at", path), `${path}.last_used_at`),
    created_at: asStringOrNull(pick(record, "created_at", path), `${path}.created_at`),
    updated_at: asStringOrNull(pick(record, "updated_at", path), `${path}.updated_at`),
  };
}

export function parseClientApiKeysResponse(value: unknown): ClientApiKeysResponse {
  const record = asRecord(value, "clientApiKeysResponse");
  return {
    status: asString(pick(record, "status", "clientApiKeysResponse"), "clientApiKeysResponse.status") as "success",
    total: asNumber(pick(record, "total", "clientApiKeysResponse"), "clientApiKeysResponse.total"),
    keys: asArray(pick(record, "keys", "clientApiKeysResponse"), "clientApiKeysResponse.keys", (item, index) =>
      parseClientApiKeyRecord(item, `clientApiKeysResponse.keys[${index}]`)
    ),
  };
}

export function parseClientApiKeyMutationResponse(value: unknown): ClientApiKeyMutationResponse {
  const record = asRecord(value, "clientApiKeyMutationResponse");
  const response: ClientApiKeyMutationResponse = {
    status: asString(
      pick(record, "status", "clientApiKeyMutationResponse"),
      "clientApiKeyMutationResponse.status"
    ) as "success",
    key: parseClientApiKeyRecord(
      pick(record, "key", "clientApiKeyMutationResponse"),
      "clientApiKeyMutationResponse.key"
    ),
  };
  const apiKey = record["api_key"];
  if (apiKey != null) {
    response.api_key = asString(apiKey, "clientApiKeyMutationResponse.api_key");
  }
  return response;
}

export function parseClientApiKeyDeleteResponse(value: unknown): ClientApiKeyDeleteResponse {
  const record = asRecord(value, "clientApiKeyDeleteResponse");
  return {
    status: asString(
      pick(record, "status", "clientApiKeyDeleteResponse"),
      "clientApiKeyDeleteResponse.status"
    ) as "success",
    deleted_id: asString(
      pick(record, "deleted_id", "clientApiKeyDeleteResponse"),
      "clientApiKeyDeleteResponse.deleted_id"
    ),
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
    is_active: asBoolean(pick(record, "is_active", "workspaceDetailResponse"), "workspaceDetailResponse.is_active"),
    groups: asArray(pick(record, "groups", "workspaceDetailResponse"), "workspaceDetailResponse.groups", (item, index) =>
      parseWorkspaceGroupRef(item, `workspaceDetailResponse.groups[${index}]`)
    ),
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
