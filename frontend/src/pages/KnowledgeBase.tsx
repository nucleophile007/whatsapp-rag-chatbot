import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { getCollections, createCollection, uploadDocuments, syncCollections } from "../lib/api";
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
} from "lucide-react";
import { cn } from "../lib/utils";
import type { Collection } from "../lib/types";

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

export default function KnowledgeBase() {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [websiteUrlsText, setWebsiteUrlsText] = useState("");
  const [urlMaxPages, setUrlMaxPages] = useState(120);
  const [urlUseSitemap, setUrlUseSitemap] = useState(true);
  const [chunkSize, setChunkSize] = useState(900);
  const [chunkOverlap, setChunkOverlap] = useState(180);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [uploadErrorMessage, setUploadErrorMessage] = useState("");
  const [uploadSuccessMessage, setUploadSuccessMessage] = useState("");
  const [canForceRecreate, setCanForceRecreate] = useState(false);
  const [syncStatus, setSyncStatus] = useState("");
  const websiteUrls = parseWebsiteUrls(websiteUrlsText);

  const { data, isLoading } = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
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
      chunkSize: number;
      chunkOverlap: number;
    }) =>
      uploadDocuments(vars.name, vars.files, vars.urls, {
        forceRecreate: vars.forceRecreate,
        urlMaxPages: vars.urlMaxPages,
        urlUseSitemap: vars.urlUseSitemap,
        chunkSize: vars.chunkSize,
        chunkOverlap: vars.chunkOverlap,
      }),
    onMutate: () => {
      setUploadStatus("uploading");
      setUploadErrorMessage("");
      setUploadSuccessMessage("");
      setCanForceRecreate(false);
    },
    onSuccess: (result) => {
      setUploadStatus("success");
      setUploadErrorMessage("");
      const pointsInfo = typeof result.points_count === "number" ? ` Total points now: ${result.points_count}.` : "";
      setUploadSuccessMessage(`${result.message}${pointsInfo}`);
      setCanForceRecreate(false);
      setFiles([]);
      setWebsiteUrlsText("");
      setTimeout(() => setUploadStatus("idle"), 3000);
    },
    onError: (error) => {
      setUploadStatus("error");

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

  const syncMutation = useMutation({
    mutationFn: syncCollections,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      setSyncStatus(`Sync complete. Found ${result.total_found} collections.`);
      setTimeout(() => setSyncStatus(""), 3800);
    },
  });

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

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }

  const collections = data?.collections || [];
  const resolvedSelectedKbId = selectedKbId || collections[0]?.id || null;
  const selectedKb = collections.find((collection) => collection.id === resolvedSelectedKbId) || null;

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
                <div className="panel-muted p-7 md:p-9 text-center">
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
                            chunkSize,
                            chunkOverlap,
                          })
                        }
                        disabled={uploadStatus === "uploading"}
                        className="btn-primary mt-5 w-full"
                      >
                        {uploadStatus === "uploading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                        {uploadStatus === "uploading" ? "Indexing..." : "Start Indexing"}
                      </button>
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
