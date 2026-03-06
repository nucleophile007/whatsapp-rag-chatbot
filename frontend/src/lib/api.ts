import axios from "axios";
import type {
  ApiStatusMessage,
  ClientApiKeyCreateInput,
  ClientApiKeyDeleteResponse,
  ClientApiKeyMutationResponse,
  ClientApiKeysResponse,
  ClientApiKeyUpdateInput,
  ClientChatDocsResponse,
  ClientChatRequestPayload,
  ClientChatResponse,
  CollectionRecord,
  CollectionsResponse,
  DeleteFlowResponse,
  ExecutionsResponse,
  FlowCreateInput,
  FlowDetail,
  FlowMutationResponse,
  FlowUpdateInput,
  FlowsResponse,
  GroupsResponse,
  SyncCollectionsResponse,
  SyncGroupsResponse,
  TemplatesResponse,
  TestFlowResponse,
  ToggleGroupResponse,
  ToggleWorkspaceResponse,
  UploadDocumentsResponse,
  WorkerScaleInput,
  WorkerStatusResponse,
  WorkspaceStatusInput,
  WorkspaceDetailResponse,
  WorkspaceFormInput,
  WorkspaceRecord,
  WorkspacesResponse,
} from "./types";
import {
  parseApiStatusMessage,
  parseClientApiKeyMutationResponse,
  parseClientApiKeysResponse,
  parseClientApiKeyDeleteResponse,
  parseClientChatDocsResponse,
  parseClientChatResponse,
  parseCollectionRecord,
  parseCollectionsResponse,
  parseDeleteFlowResponse,
  parseExecutionsResponse,
  parseFlowDetail,
  parseFlowMutationResponse,
  parseFlowsResponse,
  parseGroupsResponse,
  parseSyncCollectionsResponse,
  parseSyncGroupsResponse,
  parseTemplatesResponse,
  parseTestFlowResponse,
  parseToggleGroupResponse,
  parseToggleWorkspaceResponse,
  parseUploadDocumentsResponse,
  parseWorkerStatusResponse,
  parseWorkspaceDetailResponse,
  parseWorkspaceRecord,
  parseWorkspacesResponse,
} from "./validators";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

// Group APIs
export const getGroups = async (): Promise<GroupsResponse> => {
  const response = await api.get<unknown>("/api/groups");
  return parseGroupsResponse(response.data);
};

export const syncGroups = async (): Promise<SyncGroupsResponse> => {
  const response = await api.post<unknown>("/api/groups/sync");
  return parseSyncGroupsResponse(response.data);
};

export const toggleGroup = async (groupId: string): Promise<ToggleGroupResponse> => {
  const response = await api.patch<unknown>(`/api/groups/${groupId}/toggle`);
  return parseToggleGroupResponse(response.data);
};

// Flow APIs
export const getFlows = async (workspaceId?: string): Promise<FlowsResponse> => {
  const response = await api.get<unknown>("/api/flows", { params: { workspace_id: workspaceId } });
  return parseFlowsResponse(response.data);
};

export const getFlow = async (flowId: string): Promise<FlowDetail> => {
  const response = await api.get<unknown>(`/api/flows/${flowId}`);
  return parseFlowDetail(response.data);
};

export const createFlow = async (flowData: FlowCreateInput): Promise<FlowMutationResponse> => {
  const response = await api.post<unknown>("/api/flows", flowData);
  return parseFlowMutationResponse(response.data);
};

export const updateFlow = async ({
  id,
  data,
}: {
  id: string;
  data: FlowUpdateInput;
}): Promise<FlowMutationResponse> => {
  const response = await api.put<unknown>(`/api/flows/${id}`, data);
  return parseFlowMutationResponse(response.data);
};

export const deleteFlow = async (flowId: string): Promise<DeleteFlowResponse> => {
  const response = await api.delete<unknown>(`/api/flows/${flowId}`);
  return parseDeleteFlowResponse(response.data);
};

export const attachFlowToWorkspace = async ({
  workspaceId,
  flowId,
}: {
  workspaceId: string;
  flowId: string;
}): Promise<ApiStatusMessage> => {
  const response = await api.post<unknown>(`/api/workspaces/${workspaceId}/flows/${flowId}`);
  return parseApiStatusMessage(response.data);
};

export const detachFlowFromWorkspace = async ({
  workspaceId,
  flowId,
}: {
  workspaceId: string;
  flowId: string;
}): Promise<ApiStatusMessage> => {
  const response = await api.delete<unknown>(`/api/workspaces/${workspaceId}/flows/${flowId}`);
  return parseApiStatusMessage(response.data);
};

export const testFlow = async (flowId: string): Promise<TestFlowResponse> => {
  const response = await api.post<unknown>(`/api/flows/${flowId}/test`);
  return parseTestFlowResponse(response.data);
};

// Execution APIs
export const getExecutions = async (
  params: { flow_id?: string; limit?: number; offset?: number } = {}
): Promise<ExecutionsResponse> => {
  const response = await api.get<unknown>("/api/executions", { params });
  return parseExecutionsResponse(response.data);
};

// Knowledge Base (Collection) APIs
export const getCollections = async (): Promise<CollectionsResponse> => {
  const response = await api.get<unknown>("/api/collections");
  return parseCollectionsResponse(response.data);
};

export const createCollection = async (data: { name: string; description?: string }): Promise<CollectionRecord> => {
  const response = await api.post<unknown>("/api/collections", data);
  return parseCollectionRecord(response.data);
};

export const syncCollections = async (): Promise<SyncCollectionsResponse> => {
  const response = await api.post<unknown>("/api/collections/sync");
  return parseSyncCollectionsResponse(response.data);
};

export const uploadDocuments = async (
  kbName: string,
  files: File[],
  urls: string[] = [],
  options: {
    forceRecreate?: boolean;
    urlMaxPages?: number;
    urlUseSitemap?: boolean;
    chunkSize?: number;
    chunkOverlap?: number;
  } = {}
): Promise<UploadDocumentsResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  urls.forEach((url) => formData.append("urls", url));
  const queryParams: Record<string, string | number | boolean> = {};
  if (options.forceRecreate) queryParams.force_recreate = true;
  if (typeof options.urlMaxPages === "number") queryParams.url_max_pages = options.urlMaxPages;
  if (typeof options.urlUseSitemap === "boolean") queryParams.url_use_sitemap = options.urlUseSitemap;
  if (typeof options.chunkSize === "number") queryParams.chunk_size = options.chunkSize;
  if (typeof options.chunkOverlap === "number") queryParams.chunk_overlap = options.chunkOverlap;

  const response = await api.post<unknown>(`/api/collections/${kbName}/upload`, formData, {
    params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return parseUploadDocumentsResponse(response.data);
};

export const clientChatRespond = async (
  payload: ClientChatRequestPayload,
  apiKey?: string
): Promise<ClientChatResponse> => {
  const headers: Record<string, string> = {};
  if (apiKey?.trim()) headers["X-Client-Api-Key"] = apiKey.trim();
  const response = await api.post<unknown>("/api/chat/respond", payload, { headers });
  return parseClientChatResponse(response.data);
};

export type ClientChatStreamEvent =
  | { type: "meta"; data: Record<string, unknown> }
  | { type: "token"; data: { text: string } }
  | { type: "done"; data: ClientChatResponse }
  | { type: "error"; data: { detail: string } };

export const clientChatRespondStream = async (
  payload: ClientChatRequestPayload,
  onEvent: (event: ClientChatStreamEvent) => void,
  apiKey?: string
): Promise<void> => {
  const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (apiKey?.trim()) headers["X-Client-Api-Key"] = apiKey.trim();

  const response = await fetch(`${baseURL}/api/chat/respond/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const errorText = await response.text();
    throw new Error(errorText || `Streaming failed with ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushEvents = () => {
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const rawBlock of blocks) {
      const lines = rawBlock.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event: "));
      const dataLine = lines.find((line) => line.startsWith("data: "));
      if (!eventLine || !dataLine) continue;

      const eventName = eventLine.slice(7).trim();
      const payloadText = dataLine.slice(6).trim();
      let parsed: unknown;
      try {
        parsed = JSON.parse(payloadText);
      } catch {
        continue;
      }

      if (eventName === "meta") {
        onEvent({ type: "meta", data: (parsed as Record<string, unknown>) || {} });
      } else if (eventName === "token") {
        const obj = (parsed as { text?: unknown }) || {};
        onEvent({ type: "token", data: { text: typeof obj.text === "string" ? obj.text : "" } });
      } else if (eventName === "done") {
        onEvent({ type: "done", data: parseClientChatResponse(parsed) });
      } else if (eventName === "error") {
        const obj = (parsed as { detail?: unknown }) || {};
        onEvent({ type: "error", data: { detail: typeof obj.detail === "string" ? obj.detail : "Stream error" } });
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    flushEvents();
  }

  if (buffer.trim()) {
    flushEvents();
  }
};

export const getClientChatDocs = async (apiKey?: string): Promise<ClientChatDocsResponse> => {
  const headers: Record<string, string> = {};
  if (apiKey?.trim()) headers["X-Client-Api-Key"] = apiKey.trim();
  const response = await api.get<unknown>("/api/chat/docs", { headers });
  return parseClientChatDocsResponse(response.data);
};

export const getClientChatDocsForCollection = async (
  collectionName?: string,
  apiKey?: string
): Promise<ClientChatDocsResponse> => {
  const headers: Record<string, string> = {};
  if (apiKey?.trim()) headers["X-Client-Api-Key"] = apiKey.trim();
  const params = collectionName ? { collection_name: collectionName } : undefined;
  const response = await api.get<unknown>("/api/chat/docs", { headers, params });
  return parseClientChatDocsResponse(response.data);
};

function buildClientAdminHeaders(adminKey?: string, apiKey?: string): Record<string, string> {
  const headers: Record<string, string> = {};
  if (adminKey?.trim()) headers["X-Client-Admin-Key"] = adminKey.trim();
  if (apiKey?.trim()) headers["X-Client-Api-Key"] = apiKey.trim();
  return headers;
}

export const getClientApiKeys = async (
  adminKey?: string,
  apiKey?: string
): Promise<ClientApiKeysResponse> => {
  const headers = buildClientAdminHeaders(adminKey, apiKey);
  const response = await api.get<unknown>("/api/chat/keys", { headers });
  return parseClientApiKeysResponse(response.data);
};

export const createClientApiKey = async (
  payload: ClientApiKeyCreateInput,
  adminKey?: string,
  apiKey?: string
): Promise<ClientApiKeyMutationResponse> => {
  const headers = buildClientAdminHeaders(adminKey, apiKey);
  const response = await api.post<unknown>("/api/chat/keys", payload, { headers });
  return parseClientApiKeyMutationResponse(response.data);
};

export const updateClientApiKey = async (
  keyId: string,
  payload: ClientApiKeyUpdateInput,
  adminKey?: string,
  apiKey?: string
): Promise<ClientApiKeyMutationResponse> => {
  const headers = buildClientAdminHeaders(adminKey, apiKey);
  const response = await api.patch<unknown>(`/api/chat/keys/${keyId}`, payload, { headers });
  return parseClientApiKeyMutationResponse(response.data);
};

export const deleteClientApiKey = async (
  keyId: string,
  adminKey?: string,
  apiKey?: string
): Promise<ClientApiKeyDeleteResponse> => {
  const headers = buildClientAdminHeaders(adminKey, apiKey);
  const response = await api.delete<unknown>(`/api/chat/keys/${keyId}`, { headers });
  return parseClientApiKeyDeleteResponse(response.data);
};

// Workspace APIs
export const getWorkspaces = async (): Promise<WorkspacesResponse> => {
  const response = await api.get<unknown>("/api/workspaces");
  return parseWorkspacesResponse(response.data);
};

export const createWorkspace = async (data: WorkspaceFormInput): Promise<WorkspaceRecord> => {
  const response = await api.post<unknown>("/api/workspaces", data);
  return parseWorkspaceRecord(response.data);
};

export const getWorkspace = async (id: string): Promise<WorkspaceDetailResponse> => {
  const response = await api.get<unknown>(`/api/workspaces/${id}`);
  return parseWorkspaceDetailResponse(response.data);
};

export const updateWorkspace = async ({
  id,
  data,
}: {
  id: string;
  data: WorkspaceFormInput;
}): Promise<ApiStatusMessage> => {
  const response = await api.put<unknown>(`/api/workspaces/${id}`, data);
  return parseApiStatusMessage(response.data);
};

export const deleteWorkspace = async (id: string): Promise<ApiStatusMessage> => {
  const response = await api.delete<unknown>(`/api/workspaces/${id}`);
  return parseApiStatusMessage(response.data);
};

export const toggleWorkspace = async (id: string): Promise<ToggleWorkspaceResponse> => {
  const response = await api.patch<unknown>(`/api/workspaces/${id}/toggle`);
  return parseToggleWorkspaceResponse(response.data);
};

export const setWorkspaceStatus = async ({ id, is_active }: WorkspaceStatusInput): Promise<ToggleWorkspaceResponse> => {
  const response = await api.patch<unknown>(`/api/workspaces/${id}/status`, { is_active });
  return parseToggleWorkspaceResponse(response.data);
};

export const getTemplates = async (): Promise<TemplatesResponse> => {
  const response = await api.get<unknown>("/api/templates");
  return parseTemplatesResponse(response.data);
};

export const getWorkerStatus = async (): Promise<WorkerStatusResponse> => {
  const response = await api.get<unknown>("/api/workers/status");
  return parseWorkerStatusResponse(response.data);
};

export const setWorkerScale = async (data: WorkerScaleInput): Promise<WorkerStatusResponse> => {
  const response = await api.patch<unknown>("/api/workers/scale", data);
  return parseWorkerStatusResponse(response.data);
};

export default api;
