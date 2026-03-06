import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Database, Users, Sparkles, ArrowUpRight, Radar, Cpu, Loader2, RefreshCw, Activity } from "lucide-react";
import { getWorkerStatus, setWorkerScale } from "../lib/api";

const cards = [
  {
    title: "Workspaces",
    desc: "Compose AI behavior, prompt structure, and deployment scope.",
    icon: Layers,
    href: "/workspaces",
    tone: "from-cyan-500 to-teal-500",
  },
  {
    title: "Knowledge Base",
    desc: "Index PDFs and shape retrieval context quality.",
    icon: Database,
    href: "/knowledge-base",
    tone: "from-amber-500 to-orange-500",
  },
  {
    title: "Executions",
    desc: "Watch flow runtime and diagnose issues quickly.",
    icon: Users,
    href: "/executions",
    tone: "from-emerald-500 to-lime-500",
  },
];

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { data: workerStatus, isLoading: workerLoading, isFetching } = useQuery({
    queryKey: ["workers", "status"],
    queryFn: getWorkerStatus,
    refetchInterval: 5000,
  });
  const [desiredInput, setDesiredInput] = useState<string>("");

  const effectiveDesired = useMemo(() => {
    if (!workerStatus) return "";
    return String(workerStatus.desired_count);
  }, [workerStatus]);

  const scaleMutation = useMutation({
    mutationFn: setWorkerScale,
    onSuccess: (result) => {
      queryClient.setQueryData(["workers", "status"], result);
      setDesiredInput(String(result.desired_count));
    },
  });

  const desiredValue = desiredInput || effectiveDesired;
  const parsedDesired = Number.parseInt(desiredValue || "0", 10);
  const limits = workerStatus?.limits;
  const canSubmit =
    Number.isFinite(parsedDesired) &&
    !!limits &&
    parsedDesired >= limits.min &&
    parsedDesired <= limits.max &&
    parsedDesired !== workerStatus?.desired_count &&
    !scaleMutation.isPending;

  return (
    <div className="mx-auto max-w-6xl space-y-8 p-5 md:p-8">
      <section className="panel soft-grid animate-rise relative overflow-hidden p-7 md:p-9">
        <div className="absolute -right-20 -top-20 h-52 w-52 rounded-full bg-cyan-400/15" />
        <div className="absolute -bottom-20 left-1/2 h-44 w-44 rounded-full bg-amber-400/15" />

        <div className="relative flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <p className="tag border-cyan-300/50 bg-cyan-50 text-cyan-800">
              <Radar className="h-3.5 w-3.5" />
              Operations Ready
            </p>
            <h1 className="title-xl max-w-2xl">Design, deploy, and monitor your WhatsApp AI stack from one surface.</h1>
            <p className="subtitle max-w-xl">
              This console combines RAG memory, workflow automation, and runtime visibility in a single control loop.
            </p>
          </div>

          <Link to="/workspaces" className="btn-primary w-fit">
            <Sparkles className="h-4 w-4" />
            Start Building
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {cards.map((card, i) => (
          <Link
            key={card.title}
            to={card.href}
            style={{ animationDelay: `${i * 90}ms` }}
            className="panel animate-rise group p-5 transition-all hover:-translate-y-1 hover:shadow-lg"
          >
            <div className={`mb-5 inline-flex rounded-2xl bg-gradient-to-br p-3 text-white shadow ${card.tone}`}>
              <card.icon className="h-5 w-5" />
            </div>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-lg font-bold">{card.title}</h2>
              <ArrowUpRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{card.desc}</p>
          </Link>
        ))}
      </section>

      <section className="panel animate-rise p-5 md:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="tag bg-secondary text-secondary-foreground">
              <Cpu className="h-3.5 w-3.5" />
              Worker Runtime Control
            </p>
            <h2 className="mt-2 text-xl font-bold">RQ Worker Pool</h2>
            <p className="text-sm text-muted-foreground">One scheduler worker stays active; remaining workers scale for parallel job processing.</p>
          </div>
          <button
            className="btn-secondary px-3 py-2 text-xs"
            onClick={() => queryClient.invalidateQueries({ queryKey: ["workers", "status"] })}
            disabled={isFetching || workerLoading}
          >
            {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </button>
        </div>

        {workerLoading || !workerStatus ? (
          <div className="flex min-h-[120px] items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Desired</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.desired_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Active</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.active_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Schedulers</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.scheduler_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Queued</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.queued_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Processing</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.processing_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Scheduled</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.scheduled_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Finished</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.finished_count}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Failed</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.failed_count}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Flow Total ({workerStatus.flow_runtime.window_minutes}m)
                </p>
                <p className="mt-1 text-lg font-bold">{workerStatus.flow_runtime.recent_total}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow Running</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.flow_runtime.running_now}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow Completed</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.flow_runtime.recent_completed}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow Failed</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.flow_runtime.recent_failed}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Stale Auto-Fixed</p>
                <p className="mt-1 text-lg font-bold">{workerStatus.flow_runtime.stale_cleaned}</p>
              </div>
              <div className="panel-muted p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Flow Metrics</p>
                <p className="mt-1 text-sm font-semibold">
                  {workerStatus.flow_runtime.error ? "Error" : "Healthy"}
                </p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Fast jobs may skip visible queue time and move directly to <span className="font-semibold">Finished</span>.
            </p>

            <div className="panel-muted p-3">
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Desired Worker Count ({workerStatus.limits.min}-{workerStatus.limits.max})
                  </span>
                  <input
                    type="number"
                    min={workerStatus.limits.min}
                    max={workerStatus.limits.max}
                    value={desiredValue}
                    onChange={(event) => setDesiredInput(event.target.value)}
                    className="input-base w-44"
                  />
                </label>
                <button
                  className="btn-primary px-3 py-2 text-xs"
                  disabled={!canSubmit}
                  onClick={() => {
                    if (!Number.isFinite(parsedDesired)) return;
                    scaleMutation.mutate({ desired_count: parsedDesired });
                  }}
                >
                  {scaleMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
                  Apply Scale
                </button>
              </div>
              {scaleMutation.isError && (
                <p className="mt-2 text-xs text-destructive">Failed to scale workers. Please retry.</p>
              )}
            </div>

            <div className="space-y-2">
              {workerStatus.workers.map((worker) => (
                <div key={worker.name} className="panel flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{worker.name}</p>
                    <p className="text-xs text-muted-foreground">Queues: {worker.queues.join(", ") || "default"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="tag">{worker.is_scheduler ? "Scheduler" : "Worker"}</span>
                    <span className="tag border-slate-200 bg-slate-50 text-slate-700">{worker.state}</span>
                  </div>
                </div>
              ))}
              {workerStatus.workers.length === 0 && (
                <div className="panel-muted p-3 text-sm text-muted-foreground">No active workers detected.</div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
