import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  getCollections,
  createCollection,
  startUploadDocuments,
  getUploadJobStatus,
  syncCollections,
  evaluateRag,
  getCollectionRetrievalProfile,
  updateCollectionRetrievalProfile,
} from "../lib/api";
import {
  Loader2,
  Plus,
  Database,
  FileUp,
  CheckCircle,
  AlertCircle,
  FileText,
  RefreshCcw,
  Search,
  Globe,
  Gauge,
  FlaskConical,
  Trash2,
} from "lucide-react";
import { cn } from "../lib/utils";
import type {
  Collection,
  RagEvalCaseInput,
  RagEvalResponse,
  RetrievalProfile,
  RetrievalProfileUpdateInput,
} from "../lib/types";

const parseWebsiteUrls = (rawText: string): string[] =>
  Array.from(
    new Set(
      rawText
        .replaceAll(",", "\n")
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );

const parseExpectedTokens = (rawText: string): string[] =>
  Array.from(
    new Set(
      rawText
        .replaceAll("|", ",")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );

const parseApiErrorMessage = (error: unknown, fallback: string): string => {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }
  const responseData = error.response?.data as { detail?: unknown; message?: unknown } | undefined;
  const detail = responseData?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: unknown }).msg || "");
        return "";
      })
      .filter((value) => value.trim().length > 0);
    if (parts.length > 0) {
      return parts.join(" | ");
    }
  }
  if (typeof responseData?.message === "string" && responseData.message.trim()) {
    return responseData.message;
  }
  if (typeof error.message === "string" && error.message.trim()) {
    return error.message;
  }
  return fallback;
};

const PROFILE_FALLBACKS = {
  final_context_k: 8,
  retrieval_candidates: 24,
  grounding_threshold: 0.44,
  require_citations: true,
  min_context_chars: 220,
  query_variants_limit: 4,
  clarification_enabled: true,
  clarification_threshold: 0.58,
  chunk_size: 900,
  chunk_overlap: 180,
};

type RetrievalProfileFormState = {
  final_context_k: number;
  retrieval_candidates: number;
  grounding_threshold: number;
  require_citations: boolean;
  min_context_chars: number;
  query_variants_limit: number;
  clarification_enabled: boolean;
  clarification_threshold: number;
  chunk_size: number;
  chunk_overlap: number;
};

const resolveProfileForm = (
  profile: RetrievalProfile | null | undefined,
  defaults?: { chunk_size: number; chunk_overlap: number }
): RetrievalProfileFormState => ({
  final_context_k: profile?.final_context_k ?? PROFILE_FALLBACKS.final_context_k,
  retrieval_candidates: profile?.retrieval_candidates ?? PROFILE_FALLBACKS.retrieval_candidates,
  grounding_threshold: profile?.grounding_threshold ?? PROFILE_FALLBACKS.grounding_threshold,
  require_citations: profile?.require_citations ?? PROFILE_FALLBACKS.require_citations,
  min_context_chars: profile?.min_context_chars ?? PROFILE_FALLBACKS.min_context_chars,
  query_variants_limit: profile?.query_variants_limit ?? PROFILE_FALLBACKS.query_variants_limit,
  clarification_enabled: profile?.clarification_enabled ?? PROFILE_FALLBACKS.clarification_enabled,
  clarification_threshold: profile?.clarification_threshold ?? PROFILE_FALLBACKS.clarification_threshold,
  chunk_size: profile?.chunk_size ?? defaults?.chunk_size ?? PROFILE_FALLBACKS.chunk_size,
  chunk_overlap: profile?.chunk_overlap ?? defaults?.chunk_overlap ?? PROFILE_FALLBACKS.chunk_overlap,
});

type ProfileNumericKey = Exclude<
  keyof RetrievalProfileFormState,
  "require_citations" | "clarification_enabled"
>;

export default function KnowledgeBase() {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [websiteUrlsText, setWebsiteUrlsText] = useState("");
  const [urlMaxPages, setUrlMaxPages] = useState(120);
  const [urlUseSitemap, setUrlUseSitemap] = useState(true);
  const [pdfUseOcr, setPdfUseOcr] = useState(false);
  const [chunkSize, setChunkSize] = useState(900);
  const [chunkOverlap, setChunkOverlap] = useState(180);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [uploadErrorMessage, setUploadErrorMessage] = useState("");
  const [uploadSuccessMessage, setUploadSuccessMessage] = useState("");
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [uploadProgressPercent, setUploadProgressPercent] = useState(0);
  const [uploadPhaseLabel, setUploadPhaseLabel] = useState("");
  const [uploadProgressMessage, setUploadProgressMessage] = useState("");
  const [canForceRecreate, setCanForceRecreate] = useState(false);
  const [syncStatus, setSyncStatus] = useState("");
  const [evalCases, setEvalCases] = useState<Array<{ question: string; expectedRaw: string }>>([
    { question: "", expectedRaw: "" },
  ]);
  const [evalConversationHistory, setEvalConversationHistory] = useState("");
  const [evalSystemPrompt, setEvalSystemPrompt] = useState("");
  const [evalUserPromptTemplate, setEvalUserPromptTemplate] = useState("");
  const [evalGroundingThreshold, setEvalGroundingThreshold] = useState(0.46);
  const [evalFinalContextK, setEvalFinalContextK] = useState(8);
  const [evalRetrievalCandidates, setEvalRetrievalCandidates] = useState(22);
  const [evalRequireCitations, setEvalRequireCitations] = useState(false);
  const [evalResult, setEvalResult] = useState<RagEvalResponse | null>(null);
  const [evalError, setEvalError] = useState("");
  const [profileForm, setProfileForm] = useState<RetrievalProfileFormState>(() => resolveProfileForm(undefined));
  const [profileDefaults, setProfileDefaults] = useState({
    chunk_size: PROFILE_FALLBACKS.chunk_size,
    chunk_overlap: PROFILE_FALLBACKS.chunk_overlap,
  });
  const [profileStatus, setProfileStatus] = useState<"idle" | "saving" | "success" | "error">("idle");
  const [profileError, setProfileError] = useState("");
  const [profileSuccessMessage, setProfileSuccessMessage] = useState("");
  const websiteUrls = parseWebsiteUrls(websiteUrlsText);

  const { data, isLoading } = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
  });
  const collections = data?.collections || [];
  const resolvedSelectedKbId = selectedKbId || collections[0]?.id || null;
  const selectedKb = collections.find((collection) => collection.id === resolvedSelectedKbId) || null;

  useEffect(() => {
    if (collections.length === 0) {
      if (selectedKbId !== null) {
        setSelectedKbId(null);
      }
      return;
    }
    if (selectedKbId && !collections.some((collection) => collection.id === selectedKbId)) {
      setSelectedKbId(collections[0].id);
    }
  }, [collections, selectedKbId]);

  const retrievalProfileQuery = useQuery({
    queryKey: ["collection-retrieval-profile", selectedKb?.name],
    queryFn: () => getCollectionRetrievalProfile(selectedKb!.name),
    enabled: Boolean(selectedKb?.name),
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: createCollection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      setIsCreating(false);
      setNewName("");
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (vars: {
      name: string;
      files: File[];
      urls: string[];
      forceRecreate?: boolean;
      urlMaxPages: number;
      urlUseSitemap: boolean;
      pdfUseOcr: boolean;
      chunkSize: number;
      chunkOverlap: number;
    }) =>
      startUploadDocuments(vars.name, vars.files, vars.urls, {
        forceRecreate: vars.forceRecreate,
        urlMaxPages: vars.urlMaxPages,
        urlUseSitemap: vars.urlUseSitemap,
        pdfUseOcr: vars.pdfUseOcr,
        chunkSize: vars.chunkSize,
        chunkOverlap: vars.chunkOverlap,
      }),
    onMutate: () => {
      setUploadStatus("uploading");
      setUploadErrorMessage("");
      setUploadSuccessMessage("");
      setUploadJobId(null);
      setUploadProgressPercent(0);
      setUploadPhaseLabel("Job queued");
      setUploadProgressMessage("Preparing indexing job...");
      setCanForceRecreate(false);
    },
    onSuccess: (result) => {
      setUploadJobId(result.job_id);
      setUploadProgressPercent(Math.max(0, Math.min(100, Math.round(result.progress_percent || 0))));
      setUploadPhaseLabel(result.phase_label || "Job queued");
      setUploadProgressMessage(result.message || "Indexing job started...");
    },
    onError: (error) => {
      setUploadStatus("error");
      setUploadJobId(null);
      setUploadProgressPercent(0);
      setUploadPhaseLabel("");
      setUploadProgressMessage("");

      let message = "Upload failed. Check backend logs.";
      let allowForceRecreate = false;

      if (axios.isAxiosError(error)) {
        const responseData = error.response?.data as { detail?: unknown } | undefined;
        const detail = typeof responseData?.detail === "string" ? responseData.detail : "";

        if (detail) {
          message = detail;
        }

        if (detail.includes("force_recreate")) {
          allowForceRecreate = true;
        }
      }

      setUploadErrorMessage(message);
      setUploadSuccessMessage("");
      setCanForceRecreate(allowForceRecreate);
    },
  });

  useEffect(() => {
    if (uploadStatus !== "uploading" || !uploadJobId) return;

    let isStopped = false;
    let pollingHandle: number | null = null;

    const applyTerminalResult = (resultMessage: string) => {
      setUploadSuccessMessage(resultMessage);
      setUploadErrorMessage("");
      setCanForceRecreate(false);
      setFiles([]);
      setWebsiteUrlsText("");
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      queryClient.invalidateQueries({ queryKey: ["collection-retrieval-profile", selectedKb?.name] });
      window.setTimeout(() => setUploadStatus("idle"), 3200);
    };

    const poll = async () => {
      if (isStopped) return;
      try {
        const snapshot = await getUploadJobStatus(uploadJobId);
        if (isStopped) return;

        setUploadProgressPercent(Math.max(0, Math.min(100, Math.round(snapshot.progress_percent || 0))));
        setUploadPhaseLabel(snapshot.phase_label || snapshot.phase || "Indexing");
        setUploadProgressMessage(snapshot.message || "Indexing in progress...");

        if (snapshot.status === "completed") {
          isStopped = true;
          if (pollingHandle !== null) window.clearInterval(pollingHandle);
          setUploadJobId(null);
          setUploadStatus("success");
          const result = snapshot.result;
          const resultMessage = result
            ? `${result.message}${
                typeof result.chunk_size_used === "number"
                  ? ` Chunking used: ${result.chunk_size_used}/${result.chunk_overlap_used ?? 0}.`
                  : ""
              }${result.ocr_used ? " OCR fallback: ON." : ""}${
                typeof result.points_count === "number" ? ` Total points now: ${result.points_count}.` : ""
              }`
            : snapshot.message || "Indexing complete.";
          applyTerminalResult(resultMessage);
          return;
        }

        if (snapshot.status === "failed") {
          isStopped = true;
          if (pollingHandle !== null) window.clearInterval(pollingHandle);
          setUploadJobId(null);
          setUploadStatus("error");
          const message = snapshot.error || snapshot.message || "Indexing failed. Check backend logs.";
          setUploadErrorMessage(message);
          setUploadSuccessMessage("");
          setCanForceRecreate(message.includes("force_recreate"));
        }
      } catch (error) {
        if (isStopped) return;
        isStopped = true;
        if (pollingHandle !== null) window.clearInterval(pollingHandle);
        setUploadJobId(null);
        setUploadStatus("error");
        setUploadErrorMessage(parseApiErrorMessage(error, "Failed to poll indexing progress."));
        setUploadSuccessMessage("");
      }
    };

    poll();
    pollingHandle = window.setInterval(poll, 1000);

    return () => {
      isStopped = true;
      if (pollingHandle !== null) window.clearInterval(pollingHandle);
    };
  }, [uploadStatus, uploadJobId, queryClient, selectedKb?.name]);

  const syncMutation = useMutation({
    mutationFn: syncCollections,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      setSyncStatus(`Sync complete. Found ${result.total_found} collections.`);
      setTimeout(() => setSyncStatus(""), 3800);
    },
  });

  const retrievalProfileMutation = useMutation({
    mutationFn: (vars: { kbName: string; data: RetrievalProfileUpdateInput }) =>
      updateCollectionRetrievalProfile({ kbName: vars.kbName, data: vars.data }),
    onMutate: () => {
      setProfileStatus("saving");
      setProfileError("");
      setProfileSuccessMessage("");
    },
    onSuccess: (result) => {
      const resolved = resolveProfileForm(result.profile, result.defaults ?? profileDefaults);
      setProfileForm(resolved);
      setChunkSize(resolved.chunk_size);
      setChunkOverlap(resolved.chunk_overlap);
      setEvalGroundingThreshold(resolved.grounding_threshold);
      setEvalFinalContextK(resolved.final_context_k);
      setEvalRetrievalCandidates(resolved.retrieval_candidates);
      setEvalRequireCitations(resolved.require_citations);
      setProfileStatus("success");
      setProfileSuccessMessage("Retrieval profile saved.");
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      queryClient.invalidateQueries({ queryKey: ["collection-retrieval-profile", result.knowledge_base.name] });
      setTimeout(() => setProfileStatus("idle"), 2200);
    },
    onError: (error) => {
      setProfileStatus("error");
      const message = parseApiErrorMessage(error, "Failed to update retrieval profile.");
      setProfileError(message);
      setProfileSuccessMessage("");
    },
  });

  const evalMutation = useMutation({
    mutationFn: (vars: {
      collectionName: string;
      cases: RagEvalCaseInput[];
    }) =>
      evaluateRag({
        collection_name: vars.collectionName,
        cases: vars.cases,
        conversation_history: evalConversationHistory.trim() || undefined,
        system_prompt: evalSystemPrompt.trim() || undefined,
        user_prompt_template: evalUserPromptTemplate.trim() || undefined,
        rag_options: {
          grounding_threshold: evalGroundingThreshold,
          final_context_k: evalFinalContextK,
          retrieval_candidates: evalRetrievalCandidates,
          require_citations: evalRequireCitations,
          min_context_chars: profileForm.min_context_chars,
          query_variants_limit: profileForm.query_variants_limit,
          clarification_enabled: profileForm.clarification_enabled,
          clarification_threshold: profileForm.clarification_threshold,
        },
      }),
    onMutate: () => {
      setEvalError("");
      setEvalResult(null);
    },
    onSuccess: (result) => {
      setEvalResult(result);
      setEvalError("");
    },
    onError: (error) => {
      setEvalError(parseApiErrorMessage(error, "RAG evaluation failed. Check backend logs."));
    },
  });

  useEffect(() => {
    if (!selectedKb) return;

    const defaults = retrievalProfileQuery.data?.defaults;
    if (defaults) {
      setProfileDefaults(defaults);
    }

    const resolved = resolveProfileForm(
      retrievalProfileQuery.data?.profile ?? selectedKb.retrieval_profile,
      defaults ?? profileDefaults
    );
    setProfileForm(resolved);
    setChunkSize(resolved.chunk_size);
    setChunkOverlap(resolved.chunk_overlap);
    setEvalGroundingThreshold(resolved.grounding_threshold);
    setEvalFinalContextK(resolved.final_context_k);
    setEvalRetrievalCandidates(resolved.retrieval_candidates);
    setEvalRequireCitations(resolved.require_citations);
    setProfileStatus("idle");
    setProfileError("");
    setProfileSuccessMessage("");
  }, [selectedKb?.id, retrievalProfileQuery.data]);

  const updateProfileNumber = (key: ProfileNumericKey, value: number) => {
    setProfileForm((current) => ({ ...current, [key]: value }));
    if (key === "chunk_size") {
      setChunkSize(value);
    }
    if (key === "chunk_overlap") {
      setChunkOverlap(value);
    }
  };

  const resetProfileForm = () => {
    const resolved = resolveProfileForm(undefined, profileDefaults);
    setProfileForm(resolved);
    setChunkSize(resolved.chunk_size);
    setChunkOverlap(resolved.chunk_overlap);
    setEvalGroundingThreshold(resolved.grounding_threshold);
    setEvalFinalContextK(resolved.final_context_k);
    setEvalRetrievalCandidates(resolved.retrieval_candidates);
    setEvalRequireCitations(resolved.require_citations);
    setProfileStatus("idle");
    setProfileError("");
    setProfileSuccessMessage("");
  };

  const saveProfile = () => {
    if (!selectedKb) return;
    if (profileForm.chunk_overlap >= profileForm.chunk_size) {
      setProfileStatus("error");
      setProfileError("Chunk overlap must be smaller than chunk size.");
      setProfileSuccessMessage("");
      return;
    }
    if (profileForm.retrieval_candidates < profileForm.final_context_k + 2) {
      setProfileStatus("error");
      setProfileError("Retrieval candidates should be at least final context K + 2.");
      setProfileSuccessMessage("");
      return;
    }
    retrievalProfileMutation.mutate({
      kbName: selectedKb.name,
      data: profileForm,
    });
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setFiles(Array.from(event.target.files));
      setUploadStatus("idle");
      setUploadErrorMessage("");
      setCanForceRecreate(false);
    }
  };

  const handleUrlInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setWebsiteUrlsText(event.target.value);
    setUploadStatus("idle");
    setUploadErrorMessage("");
    setCanForceRecreate(false);
  };

  const updateEvalCase = (index: number, field: "question" | "expectedRaw", value: string) => {
    setEvalCases((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row))
    );
  };

  const addEvalCase = () => {
    setEvalCases((current) => [...current, { question: "", expectedRaw: "" }]);
  };

  const removeEvalCase = (index: number) => {
    setEvalCases((current) => {
      if (current.length <= 1) return [{ question: "", expectedRaw: "" }];
      return current.filter((_, rowIndex) => rowIndex !== index);
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-7 p-5 md:p-8">
      <section className="panel animate-rise flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div className="page-header">
          <p className="tag bg-secondary text-secondary-foreground">
            <Database className="h-3.5 w-3.5" />
            RAG Memory Layer
          </p>
          <h1 className="title-xl">Knowledge Base</h1>
          <p className="subtitle">Create collections, sync from Qdrant, and index PDFs or website links for retrieval context.</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="btn-secondary"
            title="Scan Qdrant for existing collections"
          >
            <RefreshCcw className={cn("h-4 w-4", syncMutation.isPending && "animate-spin")} />
            Sync Qdrant
          </button>
          <button onClick={() => setIsCreating(true)} className="btn-primary">
            <Plus className="h-4 w-4" />
            New Collection
          </button>
        </div>
      </section>

      {syncStatus && (
        <div className="tag animate-rise border-emerald-200 bg-emerald-50 text-emerald-700">
          <CheckCircle className="h-3.5 w-3.5" />
          {syncStatus}
        </div>
      )}

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <aside className="lg:col-span-4 space-y-4">
          <div className="panel p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Collections</h2>
              <Search className="h-4 w-4 text-muted-foreground" />
            </div>

            <div className="space-y-2">
              {collections.map((collection: Collection, index: number) => (
                <button
                  key={collection.id}
                  style={{ animationDelay: `${index * 40}ms` }}
                  onClick={() => setSelectedKbId(collection.id)}
                  className={cn(
                    "animate-rise w-full rounded-xl border px-3 py-3 text-left transition-colors",
                    resolvedSelectedKbId === collection.id ? "border-primary/40 bg-primary/5" : "bg-white hover:bg-secondary"
                  )}
                >
                  <p className="text-sm font-semibold">{collection.name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Created {new Date(collection.created_at).toLocaleDateString()}</p>
                </button>
              ))}
            </div>

            {collections.length === 0 && !isCreating && (
              <div className="panel-muted mt-3 p-6 text-center text-sm text-muted-foreground">No collections found.</div>
            )}

            {isCreating && (
              <div className="panel mt-3 space-y-3 p-3">
                <input
                  autoFocus
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="Collection name"
                  className="input-base"
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && newName.trim()) createMutation.mutate({ name: newName.trim() });
                    if (event.key === "Escape") setIsCreating(false);
                  }}
                />
                <div className="flex justify-end gap-2">
                  <button onClick={() => setIsCreating(false)} className="btn-secondary px-3 py-2 text-xs">
                    Cancel
                  </button>
                  <button
                    onClick={() => createMutation.mutate({ name: newName.trim() })}
                    disabled={!newName.trim() || createMutation.isPending}
                    className="btn-primary px-3 py-2 text-xs"
                  >
                    {createMutation.isPending ? "Creating..." : "Create"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </aside>

        <div className="lg:col-span-8">
          {selectedKb ? (
            <section className="panel animate-rise overflow-hidden">
              <div className="border-b border-border/70 bg-secondary/40 p-6">
                <h2 className="text-2xl font-bold">{selectedKb.name}</h2>
                <p className="subtitle">{selectedKb.description || "Upload PDFs and website links, then index them into vectors."}</p>
              </div>

              <div className="p-6 md:p-8">
                <div className="rounded-2xl border border-border/70 bg-white p-5 text-left md:p-6">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="tag bg-secondary text-secondary-foreground">
                        <Gauge className="h-3.5 w-3.5" />
                        Collection Retrieval Profile
                      </p>
                      <h3 className="mt-2 text-lg font-bold">Tune Defaults for This Knowledge Base</h3>
                      <p className="text-sm text-muted-foreground">
                        These settings are reused for live answering and as defaults for new indexing runs.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={resetProfileForm} className="btn-secondary px-3 py-2 text-xs">
                        Reset Fields
                      </button>
                      <button
                        onClick={saveProfile}
                        disabled={
                          profileStatus === "saving" ||
                          retrievalProfileMutation.isPending ||
                          retrievalProfileQuery.isError
                        }
                        className="btn-primary px-3 py-2 text-xs"
                      >
                        {profileStatus === "saving" || retrievalProfileMutation.isPending ? "Saving..." : "Save Profile"}
                      </button>
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Final context K</span>
                      <input
                        type="number"
                        min={2}
                        max={32}
                        value={profileForm.final_context_k}
                        onChange={(event) =>
                          updateProfileNumber("final_context_k", Number(event.target.value || PROFILE_FALLBACKS.final_context_k))
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Retrieval candidates</span>
                      <input
                        type="number"
                        min={4}
                        max={128}
                        value={profileForm.retrieval_candidates}
                        onChange={(event) =>
                          updateProfileNumber(
                            "retrieval_candidates",
                            Number(event.target.value || PROFILE_FALLBACKS.retrieval_candidates)
                          )
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Grounding threshold</span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        value={profileForm.grounding_threshold}
                        onChange={(event) =>
                          updateProfileNumber(
                            "grounding_threshold",
                            Number(event.target.value || PROFILE_FALLBACKS.grounding_threshold)
                          )
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Min context chars</span>
                      <input
                        type="number"
                        min={40}
                        max={20000}
                        value={profileForm.min_context_chars}
                        onChange={(event) =>
                          updateProfileNumber(
                            "min_context_chars",
                            Number(event.target.value || PROFILE_FALLBACKS.min_context_chars)
                          )
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Query variants limit</span>
                      <input
                        type="number"
                        min={1}
                        max={8}
                        value={profileForm.query_variants_limit}
                        onChange={(event) =>
                          updateProfileNumber(
                            "query_variants_limit",
                            Number(event.target.value || PROFILE_FALLBACKS.query_variants_limit)
                          )
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Clarification threshold</span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        value={profileForm.clarification_threshold}
                        onChange={(event) =>
                          updateProfileNumber(
                            "clarification_threshold",
                            Number(event.target.value || PROFILE_FALLBACKS.clarification_threshold)
                          )
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Chunk size</span>
                      <input
                        type="number"
                        min={200}
                        max={8000}
                        value={profileForm.chunk_size}
                        onChange={(event) =>
                          updateProfileNumber("chunk_size", Number(event.target.value || PROFILE_FALLBACKS.chunk_size))
                        }
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Chunk overlap</span>
                      <input
                        type="number"
                        min={0}
                        max={2000}
                        value={profileForm.chunk_overlap}
                        onChange={(event) =>
                          updateProfileNumber("chunk_overlap", Number(event.target.value || PROFILE_FALLBACKS.chunk_overlap))
                        }
                        className="input-base"
                      />
                    </label>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-4">
                    <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={profileForm.require_citations}
                        onChange={(event) =>
                          setProfileForm((current) => ({ ...current, require_citations: event.target.checked }))
                        }
                        className="h-4 w-4"
                      />
                      Require citations
                    </label>
                    <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={profileForm.clarification_enabled}
                        onChange={(event) =>
                          setProfileForm((current) => ({ ...current, clarification_enabled: event.target.checked }))
                        }
                        className="h-4 w-4"
                      />
                      Clarification mode
                    </label>
                  </div>

                  {retrievalProfileQuery.isLoading && (
                    <p className="mt-3 inline-flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading profile...
                    </p>
                  )}
                  {retrievalProfileQuery.isError && (
                    <p className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-destructive">
                      <AlertCircle className="h-4 w-4" />
                      {parseApiErrorMessage(
                        retrievalProfileQuery.error,
                        "Unable to load retrieval profile for this collection."
                      )}
                    </p>
                  )}
                  {profileStatus === "success" && profileSuccessMessage && (
                    <p className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-emerald-700">
                      <CheckCircle className="h-4 w-4" />
                      {profileSuccessMessage}
                    </p>
                  )}
                  {profileStatus === "error" && profileError && (
                    <p className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-destructive">
                      <AlertCircle className="h-4 w-4" />
                      {profileError}
                    </p>
                  )}
                </div>

                <div className="mt-6 panel-muted p-7 md:p-9 text-center">
                  <div className="mx-auto mb-4 inline-flex rounded-2xl bg-white p-3 text-primary shadow-sm">
                    <FileUp className="h-6 w-6" />
                  </div>
                  <h3 className="text-lg font-bold">Upload Documents or Website URLs</h3>
                  <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                    PDFs and website pages will be chunked and embedded for semantic retrieval in this collection.
                  </p>

                  <div className="mx-auto mt-5 max-w-xl text-left">
                    <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Website URLs (one per line or comma-separated)
                    </label>
                    <textarea
                      value={websiteUrlsText}
                      onChange={handleUrlInputChange}
                      className="input-base min-h-24 resize-y"
                      placeholder="https://example.com&#10;https://example.com/docs"
                    />
                  </div>

                  <div className="mx-auto mt-4 grid max-w-xl grid-cols-1 gap-3 text-left md:grid-cols-2">
                    <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Max pages per site
                      <input
                        type="number"
                        min={1}
                        max={2000}
                        value={urlMaxPages}
                        onChange={(event) => setUrlMaxPages(Number(event.target.value || 1))}
                        className="input-base mt-1"
                      />
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Chunk size
                      <input
                        type="number"
                        min={200}
                        max={8000}
                        value={chunkSize}
                        onChange={(event) => setChunkSize(Number(event.target.value || 200))}
                        className="input-base mt-1"
                      />
                    </label>
                    <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Chunk overlap
                      <input
                        type="number"
                        min={0}
                        max={2000}
                        value={chunkOverlap}
                        onChange={(event) => setChunkOverlap(Number(event.target.value || 0))}
                        className="input-base mt-1"
                      />
                    </label>
                    <label className="mt-5 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={urlUseSitemap}
                        onChange={(event) => setUrlUseSitemap(event.target.checked)}
                        className="h-4 w-4"
                      />
                      Use sitemap seeding
                    </label>
                    <label className="mt-5 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={pdfUseOcr}
                        onChange={(event) => setPdfUseOcr(event.target.checked)}
                        className="h-4 w-4"
                      />
                      Use OCR for scanned PDFs
                    </label>
                  </div>

                  <input type="file" multiple accept=".pdf" onChange={handleFileChange} className="hidden" id="kb-file-upload" />
                  <label htmlFor="kb-file-upload" className="btn-secondary mt-5 cursor-pointer">
                    <Plus className="h-4 w-4" />
                    Select PDF Files
                  </label>

                  {(files.length > 0 || websiteUrls.length > 0) && (
                    <div className="mx-auto mt-6 max-w-xl text-left">
                      <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <span>Selected Sources ({files.length + websiteUrls.length})</span>
                        <button
                          onClick={() => {
                            setFiles([]);
                            setWebsiteUrlsText("");
                          }}
                          className="text-destructive"
                        >
                          Clear
                        </button>
                      </div>

                      <div className="space-y-1.5">
                        {files.map((file, index) => (
                          <div key={`${file.name}-${index}`} className="panel flex items-center gap-2 px-3 py-2">
                            <FileText className="h-4 w-4 text-primary" />
                            <span className="flex-1 truncate text-sm">{file.name}</span>
                            <span className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(0)} KB</span>
                          </div>
                        ))}
                        {websiteUrls.map((url, index) => (
                          <div key={`${url}-${index}`} className="panel flex items-center gap-2 px-3 py-2">
                            <Globe className="h-4 w-4 text-primary" />
                            <span className="flex-1 truncate text-sm">{url}</span>
                            <span className="text-xs text-muted-foreground">URL</span>
                          </div>
                        ))}
                      </div>

                      <button
                        onClick={() =>
                          selectedKb &&
                          uploadMutation.mutate({
                            name: selectedKb.name,
                            files,
                            urls: websiteUrls,
                            urlMaxPages,
                            urlUseSitemap,
                            pdfUseOcr,
                            chunkSize,
                            chunkOverlap,
                          })
                        }
                        disabled={uploadStatus === "uploading"}
                        className="btn-primary mt-5 w-full"
                      >
                        {uploadStatus === "uploading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                        {uploadStatus === "uploading"
                          ? `Indexing... ${Math.round(uploadProgressPercent)}%`
                          : "Start Indexing"}
                      </button>

                      {uploadStatus === "uploading" && (
                        <div className="mt-3 rounded-xl border border-primary/20 bg-primary/5 p-3">
                          <div className="mb-1.5 flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-wide text-primary">
                            <span>{uploadPhaseLabel || "Indexing in progress"}</span>
                            <span>{Math.round(uploadProgressPercent)}%</span>
                          </div>
                          <div className="h-2 w-full overflow-hidden rounded-full bg-primary/20">
                            <div
                              className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                              style={{ width: `${Math.max(2, Math.min(100, uploadProgressPercent))}%` }}
                            />
                          </div>
                          <p className="mt-1.5 text-xs text-muted-foreground">
                            {uploadProgressMessage || "Preparing chunks and embeddings..."}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {uploadStatus === "success" && (
                    <p className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-emerald-700">
                      <CheckCircle className="h-4 w-4" />
                      {uploadSuccessMessage || "Indexing complete."}
                    </p>
                  )}

                  {uploadStatus === "error" && (
                    <div className="mt-5 flex flex-col items-center gap-3">
                      <p className="inline-flex items-center gap-2 text-sm font-semibold text-destructive">
                        <AlertCircle className="h-4 w-4" />
                        {uploadErrorMessage || "Upload failed. Check backend logs."}
                      </p>
                      {canForceRecreate && selectedKb && (files.length > 0 || websiteUrls.length > 0) && (
                        <button
                          onClick={() =>
                              uploadMutation.mutate({
                                name: selectedKb.name,
                                files,
                                urls: websiteUrls,
                                forceRecreate: true,
                                urlMaxPages,
                                urlUseSitemap,
                                pdfUseOcr,
                                chunkSize,
                                chunkOverlap,
                              })
                            }
                          disabled={uploadMutation.isPending}
                          className="btn-secondary"
                        >
                          Recreate Collection & Reindex
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <div className="mt-6 rounded-2xl border border-border/70 bg-white p-5 text-left md:p-6">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="tag bg-secondary text-secondary-foreground">
                        <FlaskConical className="h-3.5 w-3.5" />
                        RAG Quality Lab
                      </p>
                      <h3 className="mt-2 text-lg font-bold">Evaluate and Tune Retrieval</h3>
                      <p className="text-sm text-muted-foreground">
                        Run test questions on this collection, inspect fallback/grounding rates, and tune live options.
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        setEvalResult(null);
                        setEvalError("");
                      }}
                      className="btn-secondary px-3 py-2 text-xs"
                    >
                      Clear Results
                    </button>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Grounding threshold</span>
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        value={evalGroundingThreshold}
                        onChange={(event) => setEvalGroundingThreshold(Number(event.target.value || 0))}
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Final context K</span>
                      <input
                        type="number"
                        min={2}
                        max={20}
                        value={evalFinalContextK}
                        onChange={(event) => setEvalFinalContextK(Number(event.target.value || 2))}
                        className="input-base"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Retrieval candidates</span>
                      <input
                        type="number"
                        min={6}
                        max={80}
                        value={evalRetrievalCandidates}
                        onChange={(event) => setEvalRetrievalCandidates(Number(event.target.value || 6))}
                        className="input-base"
                      />
                    </label>
                    <label className="mt-6 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={evalRequireCitations}
                        onChange={(event) => setEvalRequireCitations(event.target.checked)}
                        className="h-4 w-4"
                      />
                      Require citations
                    </label>
                  </div>

                  <div className="mt-4 grid gap-3">
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Conversation history (optional)</span>
                      <textarea
                        value={evalConversationHistory}
                        onChange={(event) => setEvalConversationHistory(event.target.value)}
                        className="input-base min-h-20 resize-y"
                        placeholder="User: cs means computer science"
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System prompt override (optional)</span>
                      <textarea
                        value={evalSystemPrompt}
                        onChange={(event) => setEvalSystemPrompt(event.target.value)}
                        className="input-base min-h-20 resize-y"
                        placeholder="Leave empty to use backend default grounding prompt."
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">User prompt template (optional)</span>
                      <textarea
                        value={evalUserPromptTemplate}
                        onChange={(event) => setEvalUserPromptTemplate(event.target.value)}
                        className="input-base min-h-20 resize-y"
                        placeholder="Question: {{query}}"
                      />
                    </label>
                  </div>

                  <div className="mt-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold uppercase tracking-[0.12em] text-muted-foreground">Evaluation Cases</h4>
                      <button onClick={addEvalCase} className="btn-secondary px-3 py-2 text-xs">
                        <Plus className="h-3.5 w-3.5" />
                        Add Case
                      </button>
                    </div>

                    <div className="space-y-2">
                      {evalCases.map((row, index) => (
                        <div key={`eval-case-${index}`} className="rounded-xl border border-border/70 bg-secondary/20 p-3">
                          <div className="mb-2 flex items-center justify-between">
                            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Case {index + 1}</p>
                            <button
                              onClick={() => removeEvalCase(index)}
                              className="inline-flex items-center gap-1 text-xs font-semibold text-destructive"
                              aria-label={`Remove case ${index + 1}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Remove
                            </button>
                          </div>
                          <label className="space-y-1.5">
                            <span className="text-xs text-muted-foreground">Question</span>
                            <input
                              value={row.question}
                              onChange={(event) => updateEvalCase(index, "question", event.target.value)}
                              className="input-base"
                              placeholder="What is Item Exporters?"
                            />
                          </label>
                          <label className="mt-2 block space-y-1.5">
                            <span className="text-xs text-muted-foreground">Expected tokens (comma separated, optional)</span>
                            <input
                              value={row.expectedRaw}
                              onChange={(event) => updateEvalCase(index, "expectedRaw", event.target.value)}
                              className="input-base"
                              placeholder="export, data"
                            />
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      if (!selectedKb) return;
                      const cases = evalCases
                        .map((row) => ({
                          question: row.question.trim(),
                          expected_contains: parseExpectedTokens(row.expectedRaw),
                        }))
                        .filter((row) => row.question.length > 0);
                      if (cases.length === 0) {
                        setEvalError("Add at least one question before running evaluation.");
                        setEvalResult(null);
                        return;
                      }
                      evalMutation.mutate({ collectionName: selectedKb.name, cases });
                    }}
                    disabled={evalMutation.isPending}
                    className="btn-primary mt-5 w-full"
                  >
                    {evalMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Gauge className="h-4 w-4" />}
                    {evalMutation.isPending ? "Running Evaluation..." : "Run Evaluation"}
                  </button>

                  {evalError && (
                    <p className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-destructive">
                      <AlertCircle className="h-4 w-4" />
                      {evalError}
                    </p>
                  )}

                  {evalResult && (
                    <div className="mt-5 space-y-3">
                      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Cases</p>
                          <p className="mt-1 text-lg font-bold">{evalResult.summary.total_cases}</p>
                        </div>
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Fallback Rate</p>
                          <p className="mt-1 text-lg font-bold">{(evalResult.summary.fallback_rate * 100).toFixed(0)}%</p>
                        </div>
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Grounded</p>
                          <p className="mt-1 text-lg font-bold">{(evalResult.summary.grounding_pass_rate * 100).toFixed(0)}%</p>
                        </div>
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Citation OK</p>
                          <p className="mt-1 text-lg font-bold">{(evalResult.summary.citation_ok_rate * 100).toFixed(0)}%</p>
                        </div>
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Expectation Hit</p>
                          <p className="mt-1 text-lg font-bold">{(evalResult.summary.expectation_hit_rate * 100).toFixed(0)}%</p>
                        </div>
                        <div className="panel-muted p-3">
                          <p className="text-xs uppercase tracking-wide text-muted-foreground">Avg Latency</p>
                          <p className="mt-1 text-lg font-bold">{evalResult.summary.avg_latency_ms.toFixed(0)} ms</p>
                        </div>
                      </div>

                      <div className="overflow-x-auto rounded-xl border border-border/70">
                        <table className="min-w-full text-left text-sm">
                          <thead className="bg-secondary/40 text-xs uppercase tracking-wide text-muted-foreground">
                            <tr>
                              <th className="px-3 py-2">#</th>
                              <th className="px-3 py-2">Question</th>
                              <th className="px-3 py-2">Fallback</th>
                              <th className="px-3 py-2">Grounding</th>
                              <th className="px-3 py-2">Latency</th>
                            </tr>
                          </thead>
                          <tbody>
                            {evalResult.results.map((row) => (
                              <tr key={row.index} className="border-t border-border/60">
                                <td className="px-3 py-2">{row.index}</td>
                                <td className="max-w-[420px] truncate px-3 py-2" title={row.question}>
                                  {row.question}
                                </td>
                                <td className="px-3 py-2">{row.fallback_used ? "Yes" : "No"}</td>
                                <td className="px-3 py-2">{row.grounding.score.toFixed(3)}</td>
                                <td className="px-3 py-2">{row.latency_ms.toFixed(0)} ms</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </section>
          ) : (
            <section className="panel-muted flex min-h-[360px] flex-col items-center justify-center gap-2 p-10 text-center">
              <Database className="h-9 w-9 text-muted-foreground" />
              <h3 className="text-lg font-bold">Select a Collection</h3>
              <p className="subtitle max-w-sm">Choose a collection from the left panel or create a new one to get started.</p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}
