import axios from "axios";

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

// Group APIs
export const getGroups = async () => {
    const response = await api.get("/api/groups");
    return response.data;
};

export const syncGroups = async () => {
    const response = await api.post("/api/groups/sync");
    return response.data;
};

export const toggleGroup = async (groupId: string) => {
    const response = await api.patch(`/api/groups/${groupId}/toggle`);
    return response.data;
};

// Flow APIs
export const getFlows = async (workspaceId?: string) => {
    const response = await api.get("/api/flows", { params: { workspace_id: workspaceId } });
    return response.data;
};

export const getFlow = async (flowId: string) => {
    const response = await api.get(`/api/flows/${flowId}`);
    return response.data;
};

export const createFlow = async (flowData: any) => {
    const response = await api.post("/api/flows", flowData);
    return response.data;
};

export const updateFlow = async ({ id, data }: { id: string; data: any }) => {
    const response = await api.put(`/api/flows/${id}`, data);
    return response.data;
};

export const deleteFlow = async (flowId: string) => {
    const response = await api.delete(`/api/flows/${flowId}`);
    return response.data;
};

export const testFlow = async (flowId: string) => {
    const response = await api.post(`/api/flows/${flowId}/test`);
    return response.data;
};

// Execution APIs
export const getExecutions = async (params: { flow_id?: string; limit?: number; offset?: number } = {}) => {
    const response = await api.get("/api/executions", { params });
    return response.data;
};

// Knowledge Base (Collection) APIs
export const getCollections = async () => {
    const response = await api.get("/api/collections");
    return response.data;
};

export const createCollection = async (data: { name: string; description?: string }) => {
    const response = await api.post("/api/collections", data);
    return response.data;
};

export const syncCollections = async () => {
    const response = await api.post("/api/collections/sync");
    return response.data;
};

export const uploadDocuments = async (kbName: string, files: File[]) => {
    const formData = new FormData();
    files.forEach(file => formData.append("files", file));
    const response = await api.post(`/api/collections/${kbName}/upload`, formData, {
        headers: {
            "Content-Type": "multipart/form-data",
        }
    });
    return response.data;
};

// Workspace APIs
export const getWorkspaces = async () => {
    const response = await api.get("/api/workspaces");
    return response.data;
};

export const createWorkspace = async (data: any) => {
    const response = await api.post("/api/workspaces", data);
    return response.data;
};

export const getWorkspace = async (id: string) => {
    const response = await api.get(`/api/workspaces/${id}`);
    return response.data;
};

export const updateWorkspace = async ({ id, data }: { id: string; data: any }) => {
    const response = await api.put(`/api/workspaces/${id}`, data);
    return response.data;
};

export const deleteWorkspace = async (id: string) => {
    const response = await api.delete(`/api/workspaces/${id}`);
    return response.data;
};

export const toggleWorkspace = async (id: string) => {
    const response = await api.patch(`/api/workspaces/${id}/toggle`);
    return response.data;
};

export const getTemplates = async () => {
    const response = await api.get("/api/templates");
    return response.data;
};

export default api;
