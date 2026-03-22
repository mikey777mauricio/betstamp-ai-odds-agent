"use client";

import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { triggerBriefing, getBriefingStatus, healthCheck, streamBriefingProgress, evaluateBriefing, uploadData, resetData, loadAltData, getDataGames, BriefingResult, ToolCall, EvaluationResult } from "@/lib/api";
import { TOOL_LABELS, getToolStage } from "@/lib/tools";
import BriefingDisplay from "@/components/BriefingDisplay";
import ChatInterface from "@/components/ChatInterface";

function getStageColor(stage: string): string {
  if (stage === "Data Collection") return "text-sky-600 bg-sky-50 border-sky-200";
  if (stage === "Anomaly Detection") return "text-red-600 bg-red-50 border-red-200";
  if (stage === "Market Analysis") return "text-purple-600 bg-purple-50 border-purple-200";
  if (stage === "Calculations") return "text-indigo-600 bg-indigo-50 border-indigo-200";
  return "text-gray-600 bg-gray-50 border-gray-200";
}

function getStageDot(stage: string): string {
  if (stage === "Data Collection") return "bg-sky-500";
  if (stage === "Anomaly Detection") return "bg-red-500";
  if (stage === "Market Analysis") return "bg-purple-500";
  if (stage === "Calculations") return "bg-indigo-500";
  return "bg-gray-500";
}

type AppStatus = "idle" | "generating" | "ready" | "error" | "no-api-key";

interface LiveToolCall {
  tool: string;
  input: Record<string, unknown>;
  stage: string;
}

export default function Home() {
  const [status, setStatus] = useState<AppStatus>("idle");
  const [briefing, setBriefing] = useState<BriefingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const [liveTools, setLiveTools] = useState<LiveToolCall[]>([]);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [runEval, setRunEval] = useState(true);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Dataset management
  type DatasetSource = "sample" | "alt" | "upload";
  interface DatasetEntry { name: string; source: DatasetSource; data: unknown | null; gameCount: number }
  const [datasets, setDatasets] = useState<DatasetEntry[]>([
    { name: "March 20 Slate (10 games, 8 books)", source: "sample", data: null, gameCount: 10 },
    { name: "March 22 Slate (5 games, 6 books)", source: "alt", data: null, gameCount: 5 },
  ]);
  const [activeDataset, setActiveDataset] = useState(0);
  const [datasetLoading, setDatasetLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    healthCheck()
      .then((h) => {
        setApiReady(true);
        if (!h.api_key_configured) setStatus("no-api-key");
      })
      .catch(() => setApiReady(false));
  }, []);

  const pollStatus = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const result = await getBriefingStatus();
        if (result.status === "ready" && result.briefing) {
          setBriefing(result.briefing);
          setStatus("ready");
          if (timerRef.current) clearInterval(timerRef.current);
          if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }
          clearInterval(interval);
          // Auto-run evaluation if toggle is on
          if (runEval) {
            setEvalLoading(true);
            evaluateBriefing()
              .then(setEvaluation)
              .catch(() => {})
              .finally(() => setEvalLoading(false));
          }
        } else if (result.status === "error") {
          setError(result.error || "Unknown error");
          setStatus("error");
          if (timerRef.current) clearInterval(timerRef.current);
          if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }
          clearInterval(interval);
        } else if (result.status === "idle") {
          // Backend restarted and lost state
          setError("Generation was interrupted. Please try again.");
          setStatus("error");
          if (timerRef.current) clearInterval(timerRef.current);
          if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }
          clearInterval(interval);
        }
      } catch {
        // Keep polling
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [runEval]);

  useEffect(() => {
    if (status === "generating") {
      const cleanup = pollStatus();
      return cleanup;
    }
  }, [status, pollStatus]);

  const handleTrigger = async () => {
    setStatus("generating");
    setError(null);
    setLiveTools([]);
    setElapsedTime(0);
    setEvaluation(null);

    // Start elapsed timer
    timerRef.current = setInterval(() => {
      setElapsedTime((t) => t + 1);
    }, 1000);

    try {
      await triggerBriefing();

      // Start SSE stream for live tool calls
      if (cleanupRef.current) cleanupRef.current();
      cleanupRef.current = streamBriefingProgress(
        (tool, input) => {
          setLiveTools((prev) => [
            ...prev,
            { tool, input, stage: getToolStage(tool) },
          ]);
        },
        () => {
          // SSE done — polling will handle the final status
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger briefing");
      setStatus("error");
      if (timerRef.current) clearInterval(timerRef.current);
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (cleanupRef.current) cleanupRef.current();
    };
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      // Support both formats: {odds: [...]} or raw array
      const payload = Array.isArray(parsed) ? { description: file.name, odds: parsed } : parsed;
      if (!payload.odds || !Array.isArray(payload.odds)) {
        setError("Invalid JSON: expected { \"odds\": [...] } or an array of odds records");
        return;
      }
      setDatasetLoading(true);
      const result = await uploadData(payload);
      const newEntry: DatasetEntry = {
        name: `${file.name} (${result.games} games)`,
        source: "upload",
        data: payload,
        gameCount: result.games,
      };
      setDatasets(prev => [...prev, newEntry]);
      setActiveDataset(datasets.length);
      setError(null);
      setBriefing(null);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file");
    } finally {
      setDatasetLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDatasetSwitch = async (index: number) => {
    if (index === activeDataset) return;
    setDatasetLoading(true);
    try {
      const ds = datasets[index];
      if (ds.source === "sample") {
        await resetData();
      } else if (ds.source === "alt") {
        await loadAltData();
      } else {
        await uploadData(ds.data);
      }
      setActiveDataset(index);
      setBriefing(null);
      setEvaluation(null);
      setStatus("idle");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch dataset");
    } finally {
      setDatasetLoading(false);
    }
  };

  // Derive current stage from latest tool call
  const currentStage = liveTools.length > 0 ? liveTools[liveTools.length - 1].stage : "Initializing";

  return (
    <div className="min-h-screen">
      {/* Top nav bar */}
      <nav className="bg-brand shadow-md border-b border-brand-dark/20">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-white/20 backdrop-blur-sm rounded-lg flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white" stroke="currentColor" strokeWidth="2">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              betstamp <span className="font-normal text-white/75">AI Odds Agent</span>
            </h1>
          </div>
          {apiReady === true && (
            <div className="flex items-center gap-2 text-white/70 text-xs">
              <span className="w-2 h-2 rounded-full bg-green-400" />
              Connected
            </div>
          )}
          {apiReady === false && (
            <div className="flex items-center gap-2 text-white/70 text-xs">
              <span className="w-2 h-2 rounded-full bg-red-400" />
              Disconnected
            </div>
          )}
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Alerts */}
        {apiReady === false && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 mb-6 text-sm text-red-700">
            Cannot connect to backend. Make sure the API server is running on port 8000.
          </div>
        )}

        {status === "no-api-key" && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 mb-6 text-sm text-amber-700">
            No API key configured. Set <code className="bg-amber-100 px-1.5 py-0.5 rounded font-mono text-xs">ANTHROPIC_API_KEY</code> in the backend .env file.
          </div>
        )}

        {/* Idle state */}
        {(status === "idle" || status === "no-api-key" || status === "error") && (
          <div className="flex flex-col items-center justify-center py-16">
            <div
              className="bg-white rounded-2xl shadow-sm border border-border p-12 text-center max-w-lg w-full"
              style={{ animation: "slideUp 0.5s ease-out" }}
            >
              <div className="w-16 h-16 bg-gradient-to-br from-brand-light to-brand/10 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-sm">
                <svg viewBox="0 0 24 24" fill="none" className="w-8 h-8 text-brand" stroke="currentColor" strokeWidth="1.5">
                  <path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-text-primary mb-2">
                Daily Market Briefing
              </h2>
              <p className="text-text-secondary text-sm mb-2">
                AI-powered analysis across multiple sportsbooks.
              </p>
              <p className="text-text-muted text-xs mb-6">
                Detects anomalies, finds arbitrage, and ranks sportsbooks — all with deterministic, tested tools.
              </p>

              {/* Dataset selector */}
              <div className="w-full mb-6">
                <div className="flex items-center gap-2">
                  <div className="flex-1 relative">
                    <select
                      value={activeDataset}
                      onChange={(e) => handleDatasetSwitch(Number(e.target.value))}
                      disabled={datasetLoading}
                      className="w-full appearance-none text-sm border border-border rounded-lg px-3 py-2 pr-8 bg-surface-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand disabled:opacity-50"
                    >
                      {datasets.map((ds, i) => (
                        <option key={i} value={i}>{ds.name}</option>
                      ))}
                    </select>
                    <svg className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={datasetLoading}
                    className="px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-surface-secondary text-text-secondary transition-colors disabled:opacity-50 whitespace-nowrap"
                  >
                    {datasetLoading ? "Loading..." : "Upload JSON"}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </div>
                <p className="text-[10px] text-text-muted mt-1.5 text-left">
                  Upload your own odds data or use the built-in sample dataset
                </p>
              </div>

              <button
                onClick={handleTrigger}
                disabled={apiReady === false || datasetLoading}
                className="px-8 py-3 bg-accent text-white rounded-xl font-semibold hover:bg-accent-dark hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed transition-all text-sm shadow-sm active:scale-[0.98]"
              >
                Generate Briefing
              </button>
              <label className="flex items-center gap-2 mt-4 cursor-pointer select-none">
                <div
                  role="switch"
                  aria-checked={runEval}
                  tabIndex={0}
                  onClick={() => setRunEval(!runEval)}
                  onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); setRunEval(!runEval); } }}
                  className={`relative w-9 h-5 rounded-full transition-colors ${runEval ? "bg-brand" : "bg-gray-300"}`}
                >
                  <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${runEval ? "translate-x-4" : ""}`} />
                </div>
                <span className="text-xs text-text-secondary">Run quality evaluation after generation</span>
              </label>
              {error && (
                <p className="text-red-500 text-sm mt-4">{error}</p>
              )}
            </div>

            {/* How It Works — expandable */}
            <HowItWorks />
          </div>
        )}

        {/* Generating state — live agent trace */}
        {status === "generating" && (
          <div className="max-w-2xl mx-auto" style={{ animation: "slideUp 0.4s ease-out" }}>
            <div className="bg-white rounded-2xl shadow-sm border border-border overflow-hidden">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border bg-surface-secondary">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <svg className="animate-spin h-5 w-5 text-brand" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <div>
                      <h2 className="text-sm font-semibold text-text-primary">Agent Running</h2>
                      <p className="text-xs text-text-muted">{currentStage}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-mono text-text-secondary">{elapsedTime}s</span>
                    {elapsedTime > 240 && (
                      <p className="text-xs text-amber-600 font-medium">Taking longer than expected...</p>
                    )}
                    <p className="text-xs text-text-muted">{liveTools.length} tool{liveTools.length !== 1 ? "s" : ""} called</p>
                  </div>
                </div>

                {/* Stage progress bar */}
                <div className="flex gap-1 mt-3">
                  {["Data Collection", "Anomaly Detection", "Market Analysis", "Calculations"].map((stage) => {
                    const hasTools = liveTools.some((t) => t.stage === stage);
                    const isActive = currentStage === stage;
                    return (
                      <div key={stage} className="flex-1 flex flex-col gap-1">
                        <div
                          className={`h-1.5 rounded-full transition-all duration-500 ${
                            hasTools
                              ? isActive
                                ? "bg-brand animate-pulse"
                                : "bg-brand"
                              : "bg-gray-200"
                          }`}
                        />
                        <span className={`text-[10px] ${hasTools ? "text-text-secondary font-medium" : "text-text-muted"}`}>
                          {stage}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Live tool call feed */}
              <div className="px-6 py-4 max-h-[400px] overflow-y-auto">
                {liveTools.length === 0 && (
                  <div className="text-center py-6 text-text-muted text-sm">
                    Waiting for agent to start calling tools...
                  </div>
                )}
                <div className="space-y-2">
                  {liveTools.map((tc, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-3 animate-[fadeIn_0.3s_ease-in]"
                      style={{ animationFillMode: "backwards", animationDelay: `${i * 50}ms` }}
                    >
                      {/* Timeline dot */}
                      <div className="flex flex-col items-center pt-1.5">
                        <div className={`w-2.5 h-2.5 rounded-full ${getStageDot(tc.stage)}`} />
                        {i < liveTools.length - 1 && (
                          <div className="w-px h-full bg-gray-200 mt-1" />
                        )}
                      </div>
                      {/* Content */}
                      <div className="flex-1 pb-2">
                        <div className="flex items-center gap-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${getStageColor(tc.stage)}`}>
                            {tc.stage}
                          </span>
                          {i === liveTools.length - 1 && (
                            <span className="flex h-2 w-2">
                              <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-brand opacity-75" />
                              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand" />
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-text-primary mt-0.5 font-medium">
                          {TOOL_LABELS[tc.tool] || tc.tool}
                        </p>
                        {tc.input && Object.keys(tc.input).length > 0 && (
                          <p className="text-xs text-text-muted font-mono mt-0.5">
                            {Object.entries(tc.input)
                              .filter(([, v]) => v !== "" && v !== null)
                              .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                              .join(", ")}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Results — Split layout: Briefing left, Chat right */}
        {status === "ready" && briefing && (
          <div className="flex flex-col lg:flex-row gap-6 items-start" style={{ animation: "slideUp 0.5s ease-out" }}>
            {/* Briefing panel — scrollable */}
            <div className="flex-1 min-w-0 w-full">
              <div className="bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
                <div className="px-6 py-3 border-b border-border bg-surface-secondary flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-text-primary">Daily Briefing</h2>
                  <button
                    onClick={handleTrigger}
                    className="px-3 py-1 text-xs text-text-muted hover:text-brand transition-colors font-medium"
                  >
                    Regenerate
                  </button>
                </div>
                <div className="p-6 max-h-[calc(100vh-180px)] overflow-y-auto">
                  <BriefingDisplay briefing={briefing} />
                </div>
              </div>

              {/* Evaluation panel */}
              {evalLoading && (
                <div className="mt-4 bg-white rounded-2xl border border-border shadow-sm p-6 flex items-center gap-3">
                  <svg className="animate-spin h-4 w-4 text-brand" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm text-text-secondary">Running quality evaluation...</span>
                </div>
              )}
              {evaluation && !evalLoading && (
                <div className="mt-4">
                  <EvaluationPanel evaluation={evaluation} />
                </div>
              )}
            </div>

            {/* Chat panel — sticky on desktop, stacked on mobile */}
            <div className="w-full lg:w-[420px] flex-shrink-0 lg:sticky top-6">
              <div className="bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
                <div className="px-6 py-3 border-b border-border bg-surface-secondary">
                  <h2 className="text-sm font-semibold text-text-primary">Follow-Up Chat</h2>
                  <p className="text-xs text-text-muted">Ask questions about the briefing</p>
                </div>
                <div className="p-4 h-[calc(100vh-220px)]">
                  <ChatInterface />
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ── How It Works ────────────────────────────────────── */

const PIPELINE_STAGES = [
  {
    key: "detect",
    label: "Detect",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.5">
        <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z" />
        <path d="M12 15.75h.008" />
      </svg>
    ),
    color: "text-red-600 bg-red-50 border-red-200",
    dotColor: "bg-red-500",
    items: ["Stale lines (timestamp lag)", "Outlier odds (MAD algorithm)", "Arbitrage opportunities"],
  },
  {
    key: "analyze",
    label: "Analyze",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
    color: "text-purple-600 bg-purple-50 border-purple-200",
    dotColor: "bg-purple-500",
    items: ["Vig/margin calculation", "Best line finder", "Sportsbook rankings", "Value opportunities"],
  },
  {
    key: "narrate",
    label: "Narrate",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.5">
        <path d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
      </svg>
    ),
    color: "text-brand bg-brand-50 border-brand/20",
    dotColor: "bg-brand",
    items: ["LLM writes executive summary", "Over pre-computed data only", "Structured Pydantic output"],
  },
];

const ARCHITECTURE_POINTS = [
  {
    title: "LLM Orchestrates, Python Computes",
    description: "All odds math runs in deterministic, tested Python functions. The LLM never does arithmetic — it calls tools and synthesizes results.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4" stroke="currentColor" strokeWidth="1.5">
        <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
      </svg>
    ),
  },
  {
    title: "Built-In Quality Evaluation",
    description: "5 automated metrics — completeness, tool coverage, anomaly recall, structured data, and narrative consistency — scored after every briefing.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4" stroke="currentColor" strokeWidth="1.5">
        <path d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
  },
  {
    title: "Contextual Follow-Up Chat",
    description: "Ask questions about the briefing. The chat agent has full access to structured data and can call the same analysis tools on demand.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4" stroke="currentColor" strokeWidth="1.5">
        <path d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
  },
  {
    title: "152 Tests, Zero LLM Math",
    description: "Comprehensive test suite covers odds math, anomaly detection, analysis tools, data store, evaluator scoring, model validation, and thread safety.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4" stroke="currentColor" strokeWidth="1.5">
        <path d="M11.42 15.17l-5.657-5.657a.75.75 0 010-1.06l.354-.354a.75.75 0 011.06 0l4.95 4.95 4.95-4.95a.75.75 0 011.06 0l.354.354a.75.75 0 010 1.06l-5.657 5.657a1.125 1.125 0 01-1.414 0z" />
        <path d="M4.5 12a7.5 7.5 0 1115 0 7.5 7.5 0 01-15 0z" />
      </svg>
    ),
  },
];

function HowItWorks() {
  const [open, setOpen] = useState(false);

  return (
    <div className="w-full max-w-2xl mt-6">
      <button
        onClick={() => setOpen(!open)}
        className="group w-full flex items-center justify-center gap-2 text-sm text-text-muted hover:text-text-secondary transition-colors py-2"
      >
        <span className="h-px flex-1 max-w-16 bg-border group-hover:bg-text-muted/30 transition-colors" />
        <span className="font-medium">How It Works</span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-4 h-4 transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
        <span className="h-px flex-1 max-w-16 bg-border group-hover:bg-text-muted/30 transition-colors" />
      </button>

      <div
        className={`overflow-hidden transition-all duration-500 ease-in-out ${
          open ? "max-h-[1200px] opacity-100 mt-4" : "max-h-0 opacity-0"
        }`}
      >
        {/* Pipeline visualization */}
        <div className="bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border bg-surface-secondary">
            <h3 className="text-sm font-semibold text-text-primary">Structured Briefing Pipeline</h3>
            <p className="text-xs text-text-muted mt-0.5">Deterministic tools produce data, LLM writes the narrative</p>
          </div>

          <div className="p-6">
            {/* 3-stage pipeline */}
            <div className="flex flex-col sm:flex-row items-stretch gap-2">
              {PIPELINE_STAGES.map((stage, i) => (
                <Fragment key={stage.key}>
                  <div className={`flex-1 rounded-xl border p-4 ${stage.color}`}>
                    <div className="flex items-center gap-2 mb-2.5">
                      <div className="w-7 h-7 rounded-lg bg-white/60 flex items-center justify-center">
                        {stage.icon}
                      </div>
                      <div>
                        <div className="text-[10px] font-mono uppercase tracking-wider opacity-60">Stage {i + 1}</div>
                        <div className="text-sm font-bold -mt-0.5">{stage.label}</div>
                      </div>
                    </div>
                    <ul className="space-y-1">
                      {stage.items.map((item) => (
                        <li key={item} className="text-xs opacity-80 flex items-start gap-1.5">
                          <span className={`w-1 h-1 rounded-full ${stage.dotColor} mt-1.5 shrink-0`} />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {i < PIPELINE_STAGES.length - 1 && (
                    <>
                      <div className="hidden sm:flex items-center justify-center shrink-0">
                        <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-text-muted" stroke="currentColor" strokeWidth="2">
                          <path d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                        </svg>
                      </div>
                      <div className="sm:hidden flex justify-center">
                        <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-text-muted" stroke="currentColor" strokeWidth="2">
                          <path d="M12 4.5v15m0 0l6.75-6.75M12 19.5l-6.75-6.75" />
                        </svg>
                      </div>
                    </>
                  )}
                </Fragment>
              ))}
            </div>

            {/* Architecture highlights */}
            <div className="mt-5 pt-5 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-3">
              {ARCHITECTURE_POINTS.map((point) => (
                <div key={point.title} className="flex gap-3 items-start">
                  <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand/10 flex items-center justify-center shrink-0 text-brand">
                    {point.icon}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-text-primary">{point.title}</div>
                    <div className="text-[11px] text-text-muted leading-relaxed mt-0.5">{point.description}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Tech stack footer */}
            <div className="mt-5 pt-4 border-t border-border flex flex-wrap items-center justify-center gap-2">
              {["Next.js", "FastAPI", "Claude Sonnet", "Strands SDK", "Pydantic", "Tailwind"].map((tech) => (
                <span key={tech} className="text-[10px] font-mono px-2 py-1 rounded-md bg-surface-secondary text-text-muted border border-border">
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Evaluation Panel ────────────────────────────────── */

const SCORE_LABELS: Record<string, { label: string; description: string }> = {
  completeness: { label: "Completeness", description: "Required briefing sections present" },
  tool_coverage: { label: "Tool Coverage", description: "Required tool categories called" },
  anomaly_recall: { label: "Anomaly Recall", description: "Known anomalies detected" },
  structured_completeness: { label: "Structured Data", description: "Structured data sections populated" },
  consistency: { label: "Consistency", description: "Narrative agrees with structured data" },
  composite_score: { label: "Composite", description: "Weighted overall quality score" },
};

function ScoreBar({ value, label, description }: { value: number; label: string; description: string }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
  const textColor = pct >= 80 ? "text-green-700" : pct >= 50 ? "text-amber-700" : "text-red-700";
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div>
          <span className="text-xs font-medium text-text-primary">{label}</span>
          <span className="text-[10px] text-text-muted ml-1.5">{description}</span>
        </div>
        <span className={`text-xs font-bold font-mono ${textColor}`}>{pct}%</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function EvaluationPanel({ evaluation }: { evaluation: EvaluationResult }) {
  const { scores } = evaluation;
  const composite = Math.round(scores.composite_score * 100);
  const compositeColor = composite >= 80 ? "text-green-700 bg-green-50 border-green-200" : composite >= 50 ? "text-amber-700 bg-amber-50 border-amber-200" : "text-red-700 bg-red-50 border-red-200";

  // Order: composite first, then individual scores
  const individualScores = Object.entries(scores).filter(([k]) => k !== "composite_score" && SCORE_LABELS[k]);

  return (
    <div className="bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
      <div className="px-6 py-3 border-b border-border bg-surface-secondary flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Quality Evaluation</h2>
          <p className="text-xs text-text-muted">Automated scoring of briefing quality</p>
        </div>
        <div className={`px-3 py-1.5 rounded-lg border font-bold text-lg font-mono ${compositeColor}`}>
          {composite}%
        </div>
      </div>
      <div className="p-6 space-y-3">
        {individualScores.map(([key, value]) => {
          const meta = SCORE_LABELS[key];
          return <ScoreBar key={key} value={value} label={meta.label} description={meta.description} />;
        })}
        <div className="pt-3 border-t border-border">
          <ScoreBar
            value={scores.composite_score}
            label="Composite Score"
            description="Weighted overall quality"
          />
        </div>
      </div>
    </div>
  );
}
