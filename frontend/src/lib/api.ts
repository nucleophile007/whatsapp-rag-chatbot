import axios from "axios";
import type {
  ApiStatusMessage,
  CollectionRecord,
  ContactsResponse,
  CollectionsResponse,
  DeleteFlowResponse,
  ExecutionBulkDeleteResponse,
  ExecutionClearResponse,
  ExecutionDeleteResponse,
  ExecutionsResponse,
  FlowCreateInput,
  FlowDetail,
  FlowMutationResponse,
  FlowUpdateInput,
  FlowsResponse,
  GroupsResponse,
  MemoryLtmMutationResponse,
  MemoryLtmUpdateInput,
  MemorySnapshotResponse,
  RagEvalRequestPayload,
  RagEvalResponse,
  RetrievalProfileResponse,
  RetrievalProfileUpdateInput,
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
  parseCollectionRecord,
  parseContactsResponse,
  parseCollectionsResponse,
  parseDeleteFlowResponse,
  parseExecutionBulkDeleteResponse,
  parseExecutionClearResponse,
  parseExecutionDeleteResponse,
  parseExecutionsResponse,
  parseFlowDetail,
  parseFlowMutationResponse,
  parseFlowsResponse,
  parseGroupsResponse,
  parseMemoryLtmMutationResponse,
  parseMemorySnapshotResponse,
  parseRagEvalResponse,
  parseRetrievalProfileResponse,
  parseSyncCollectionsResponse,
  parseSyncContactsResponse,
  parseSyncGroupsResponse,
  parseTemplatesResponse,
  parseTestFlowResponse,
  parseToggleGroupResponse,
  parseToggleWorkspaceResponse,
  parseUploadDocumentsResponse,
  parseUploadJobStartResponse,
  parseUploadJobStatusResponse,
  parseWorkerStatusResponse,
  parseWorkspaceDetailResponse,
  parseWorkspaceRecord,
  parseWorkspacesResponse,
} from "./validators";

function resolveApiBaseUrl(): string {
  const envBase = String(import.meta.env.VITE_API_URL || "").trim();
  if (envBase) {
    return envBase.replace(/\/+$/, "");
  }
  // Prefer same-origin path so Vite proxy can forward in all environments.
  return "";
}

const api = axios.create({
  baseURL: resolveApiBaseUrl(),
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

export const getContacts = async (): Promise<ContactsResponse> => {
  const response = await api.get<unknown>("/api/contacts");
  return parseContactsResponse(response.data);
};

export const syncContacts = async (): Promise<SyncContactsResponse> => {
  const response = await api.post<unknown>("/api/contacts/sync");
  return parseSyncContactsResponse(response.data);
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

export const deleteExecution = async (executionId: string): Promise<ExecutionDeleteResponse> => {
  const response = await api.delete<unknown>(`/api/executions/${executionId}`);
  return parseExecutionDeleteResponse(response.data);
};

export const deleteExecutionsBulk = async (executionIds: string[]): Promise<ExecutionBulkDeleteResponse> => {
  const response = await api.post<unknown>("/api/executions/bulk-delete", { execution_ids: executionIds });
  return parseExecutionBulkDeleteResponse(response.data);
};

export const clearExecutions = async (flowId?: string): Promise<ExecutionClearResponse> => {
  const response = await api.delete<unknown>("/api/executions", {
    params: flowId ? { flow_id: flowId } : undefined,
  });
  return parseExecutionClearResponse(response.data);
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
    pdfUseOcr?: boolean;
    chunkSize?: number;
    chunkOverlap?: number;
  } = {}
): Promise<UploadDocumentsResponse> => {
  const encodedKbName = encodeURIComponent(kbName);
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  urls.forEach((url) => formData.append("urls", url));
  const queryParams: Record<string, string | number | boolean> = {};
  if (options.forceRecreate) queryParams.force_recreate = true;
  if (typeof options.urlMaxPages === "number") queryParams.url_max_pages = options.urlMaxPages;
  if (typeof options.urlUseSitemap === "boolean") queryParams.url_use_sitemap = options.urlUseSitemap;
  if (typeof options.pdfUseOcr === "boolean") queryParams.pdf_use_ocr = options.pdfUseOcr;
  if (typeof options.chunkSize === "number") queryParams.chunk_size = options.chunkSize;
  if (typeof options.chunkOverlap === "number") queryParams.chunk_overlap = options.chunkOverlap;

  const response = await api.post<unknown>(`/api/collections/${encodedKbName}/upload`, formData, {
    params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return parseUploadDocumentsResponse(response.data);
};

export const startUploadDocuments = async (
  kbName: string,
  files: File[],
  urls: string[] = [],
  options: {
    forceRecreate?: boolean;
    urlMaxPages?: number;
    urlUseSitemap?: boolean;
    pdfUseOcr?: boolean;
    chunkSize?: number;
    chunkOverlap?: number;
  } = {}
): Promise<UploadJobStartResponse> => {
  const encodedKbName = encodeURIComponent(kbName);
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  urls.forEach((url) => formData.append("urls", url));
  const queryParams: Record<string, string | number | boolean> = {};
  if (options.forceRecreate) queryParams.force_recreate = true;
  if (typeof options.urlMaxPages === "number") queryParams.url_max_pages = options.urlMaxPages;
  if (typeof options.urlUseSitemap === "boolean") queryParams.url_use_sitemap = options.urlUseSitemap;
  if (typeof options.pdfUseOcr === "boolean") queryParams.pdf_use_ocr = options.pdfUseOcr;
  if (typeof options.chunkSize === "number") queryParams.chunk_size = options.chunkSize;
  if (typeof options.chunkOverlap === "number") queryParams.chunk_overlap = options.chunkOverlap;

  const response = await api.post<unknown>(`/api/collections/${encodedKbName}/upload/start`, formData, {
    params: Object.keys(queryParams).length > 0 ? queryParams : undefined,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return parseUploadJobStartResponse(response.data);
};

export const getUploadJobStatus = async (jobId: string): Promise<UploadJobStatusResponse> => {
  const encodedJobId = encodeURIComponent(jobId);
  const response = await api.get<unknown>(`/api/collections/upload/jobs/${encodedJobId}`);
  return parseUploadJobStatusResponse(response.data);
};

export const evaluateRag = async (payload: RagEvalRequestPayload): Promise<RagEvalResponse> => {
  const response = await api.post<unknown>("/api/rag/evaluate", payload);
  return parseRagEvalResponse(response.data);
};

export const getMemoryDebugSnapshot = async ({
  clientId,
  query,
  historyLimit,
  tokenBudget,
  ltmLimit,
  includeInactive,
  workspaceId,
  memoryScope,
}: {
  clientId: string;
  query?: string;
  historyLimit?: number;
  tokenBudget?: number;
  ltmLimit?: number;
  includeInactive?: boolean;
  workspaceId?: string;
  memoryScope?: "client" | "client_workspace";
}): Promise<MemorySnapshotResponse> => {
  const encodedClientId = encodeURIComponent(clientId);
  const response = await api.get<unknown>(`/api/memory/${encodedClientId}`, {
    params: {
      ...(query ? { query } : {}),
      ...(typeof historyLimit === "number" ? { history_limit: historyLimit } : {}),
      ...(typeof tokenBudget === "number" ? { token_budget: tokenBudget } : {}),
      ...(typeof ltmLimit === "number" ? { ltm_limit: ltmLimit } : {}),
      ...(typeof includeInactive === "boolean" ? { include_inactive: includeInactive } : {}),
      ...(workspaceId ? { workspace_id: workspaceId } : {}),
      ...(memoryScope ? { memory_scope: memoryScope } : {}),
    },
  });
  return parseMemorySnapshotResponse(response.data);
};

export const upsertMemoryLtmItem = async ({
  clientId,
  data,
  workspaceId,
  memoryScope,
}: {
  clientId: string;
  data: MemoryLtmUpdateInput;
  workspaceId?: string;
  memoryScope?: "client" | "client_workspace";
}): Promise<MemoryLtmMutationResponse> => {
  const encodedClientId = encodeURIComponent(clientId);
  const response = await api.patch<unknown>(`/api/memory/${encodedClientId}/ltm`, data, {
    params: {
      ...(workspaceId ? { workspace_id: workspaceId } : {}),
      ...(memoryScope ? { memory_scope: memoryScope } : {}),
    },
  });
  return parseMemoryLtmMutationResponse(response.data);
};

export const deactivateMemoryLtmItem = async ({
  clientId,
  memoryKey,
  workspaceId,
  memoryScope,
}: {
  clientId: string;
  memoryKey: string;
  workspaceId?: string;
  memoryScope?: "client" | "client_workspace";
}): Promise<ApiStatusMessage> => {
  const encodedClientId = encodeURIComponent(clientId);
  const response = await api.delete<unknown>(`/api/memory/${encodedClientId}/ltm`, {
    params: {
      memory_key: memoryKey,
      ...(workspaceId ? { workspace_id: workspaceId } : {}),
      ...(memoryScope ? { memory_scope: memoryScope } : {}),
    },
  });
  return parseApiStatusMessage(response.data);
};

export const clearMemoryForClient = async ({
  clientId,
  workspaceId,
  memoryScope,
}: {
  clientId: string;
  workspaceId?: string;
  memoryScope?: "client" | "client_workspace";
}): Promise<ApiStatusMessage> => {
  const encodedClientId = encodeURIComponent(clientId);
  const response = await api.delete<unknown>(`/api/memory/${encodedClientId}`, {
    params: {
      ...(workspaceId ? { workspace_id: workspaceId } : {}),
      ...(memoryScope ? { memory_scope: memoryScope } : {}),
    },
  });
  return parseApiStatusMessage(response.data);
};

export const getCollectionRetrievalProfile = async (kbName: string): Promise<RetrievalProfileResponse> => {
  const encodedKbName = encodeURIComponent(kbName);
  const response = await api.get<unknown>(`/api/collections/${encodedKbName}/retrieval-profile`);
  return parseRetrievalProfileResponse(response.data);
};

export const updateCollectionRetrievalProfile = async ({
  kbName,
  data,
}: {
  kbName: string;
  data: RetrievalProfileUpdateInput;
}): Promise<RetrievalProfileResponse> => {
  const encodedKbName = encodeURIComponent(kbName);
  const response = await api.put<unknown>(`/api/collections/${encodedKbName}/retrieval-profile`, data);
  return parseRetrievalProfileResponse(response.data);
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
  try {
    const response = await api.patch<unknown>(`/api/workspaces/${id}/status`, { is_active });
    return parseToggleWorkspaceResponse(response.data);
  } catch (_error) {
    // Browser/network fallback for environments where PATCH preflight is blocked.
    const fallback = await api.get<unknown>(`/api/workspaces/${id}/status/set`, {
      params: { is_active },
    });
    return parseToggleWorkspaceResponse(fallback.data);
  }
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
