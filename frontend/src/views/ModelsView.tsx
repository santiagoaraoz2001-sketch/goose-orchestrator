import { useState, useEffect, useCallback } from "react";
import { Save, RefreshCw, Crown, Cpu, ChevronDown, ChevronUp, Thermometer, Layers, Globe } from "lucide-react";
import { PanelCard } from "@/components/shared/PanelCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { apiGet, apiPatch } from "@/api/client";
import { COLORS } from "@/lib/design-tokens";

interface OrchestratorCfg {
  model: string;
  provider: string;
  context_window: number;
  endpoint: string;
}

interface WorkerCfg {
  model: string;
  provider: string;
  context_window: number;
  temperature: number;
  enabled: boolean;
  description: string;
}

const PROVIDERS = ["ollama", "openai", "anthropic"];

/** Dropdown for model selection. Shows fetched models as options + allows typing a custom model name. */
function ModelSelect({ value, models, onChange }: { value: string; models: string[]; onChange: (v: string) => void }) {
  const [custom, setCustom] = useState(false);

  // If the current value isn't in the fetched list, show text input mode
  const valueInList = models.length > 0 && models.includes(value);
  const showDropdown = models.length > 0 && !custom;

  return (
    <div className="flex gap-1.5 items-center">
      {showDropdown ? (
        <select
          value={valueInList ? value : "__custom__"}
          onChange={e => {
            if (e.target.value === "__custom__") {
              setCustom(true);
            } else {
              onChange(e.target.value);
            }
          }}
          className="flex-1 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
          style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}
        >
          {/* Show current value at top if it's not in the list */}
          {!valueInList && value && (
            <option value={value}>{value} (current)</option>
          )}
          {models.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
          <option value="__custom__">— enter custom model —</option>
        </select>
      ) : (
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="model:tag"
          className="flex-1 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
          style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}
        />
      )}
      {models.length > 0 && (
        <button
          onClick={() => setCustom(!custom)}
          className="px-1.5 py-1 border text-[9px] text-dim hover:text-sec transition-all shrink-0"
          style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", borderRadius: 0 }}
          title={custom ? "Show dropdown" : "Type custom model"}
        >
          {custom ? "list" : "edit"}
        </button>
      )}
    </div>
  );
}

export default function ModelsView() {
  const [orch, setOrch] = useState<OrchestratorCfg | null>(null);
  const [workers, setWorkers] = useState<Record<string, WorkerCfg>>({});
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [orchDirty, setOrchDirty] = useState(false);
  const [workerDirty, setWorkerDirty] = useState<Set<string>>(new Set());
  const [loadingModels, setLoadingModels] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [expandedWorker, setExpandedWorker] = useState<string | null>(null);

  const load = useCallback(async () => {
    const cfg = await apiGet("/api/config");
    setOrch(cfg.orchestrator);
    setWorkers(cfg.workers || {});
    setOrchDirty(false);
    setWorkerDirty(new Set());

    // Auto-fetch models for all providers in use
    const providersInUse = new Set<string>();
    if (cfg.orchestrator?.provider) providersInUse.add(cfg.orchestrator.provider);
    for (const w of Object.values(cfg.workers || {})) {
      if ((w as any).provider) providersInUse.add((w as any).provider);
    }
    for (const p of providersInUse) {
      fetchModelsQuiet(p);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Fetch without setting loadingModels spinner (for background auto-fetch)
  const fetchModelsQuiet = async (provider: string) => {
    try {
      const data = await apiGet(`/api/models/${provider}`);
      setAvailableModels(prev => ({ ...prev, [provider]: data.models || [] }));
    } catch {
      setAvailableModels(prev => ({ ...prev, [provider]: [] }));
    }
  };

  const fetchModels = async (provider: string) => {
    setLoadingModels(provider);
    try {
      const data = await apiGet(`/api/models/${provider}`);
      setAvailableModels(prev => ({ ...prev, [provider]: data.models || [] }));
    } catch {
      setAvailableModels(prev => ({ ...prev, [provider]: [] }));
    }
    setLoadingModels(null);
  };

  const updateOrch = (field: string, value: any) => {
    setOrch(prev => prev ? { ...prev, [field]: value } : prev);
    setOrchDirty(true);
  };

  const saveOrch = async () => {
    if (!orch) return;
    await apiPatch("/api/config/orchestrator", orch);
    setOrchDirty(false);
    setStatus("Orchestrator saved");
    setTimeout(() => setStatus(""), 2000);
  };

  const updateWorker = (role: string, field: string, value: any) => {
    setWorkers(prev => ({ ...prev, [role]: { ...prev[role], [field]: value } }));
    setWorkerDirty(prev => new Set(prev).add(role));
  };

  const saveWorker = async (role: string) => {
    await apiPatch(`/api/config/workers/${role}`, workers[role]);
    setWorkerDirty(prev => { const n = new Set(prev); n.delete(role); return n; });
    setStatus(`${role} saved`);
    setTimeout(() => setStatus(""), 2000);
  };

  if (!orch) return <div className="text-dim">Loading...</div>;

  const orchModels = availableModels[orch.provider] || [];

  const ROLE_META: Record<string, { accent: string; icon: string; label: string; hint: string }> = {
    deep_research: {
      accent: COLORS.blue,
      icon: "🔍",
      label: "Deep Research",
      hint: "Best with large-context models (32B+). Needs strong reasoning and factual grounding.",
    },
    local_rag: {
      accent: COLORS.teal,
      icon: "📂",
      label: "Local RAG",
      hint: "Small, fast models work well (7-14B). Needs good instruction following for retrieval tasks.",
    },
    code_gen: {
      accent: COLORS.cyan,
      icon: "💻",
      label: "Code Generation",
      hint: "Use a code-specialized model (e.g. Devstral, Qwen-Coder, DeepSeek-Coder). 14B+ recommended.",
    },
    summarizer: {
      accent: COLORS.amber,
      icon: "📝",
      label: "Summarizer",
      hint: "Small, fast models are ideal (7-14B). Low latency matters more than model size here.",
    },
    math_reasoning: {
      accent: COLORS.purple,
      icon: "🧮",
      label: "Math & Reasoning",
      hint: "Needs strong CoT reasoning. Use thinking-capable models (Qwen3, Command-R). 14B+ recommended.",
    },
    creative: {
      accent: COLORS.pink,
      icon: "✨",
      label: "Creative Writing",
      hint: "Larger models produce better prose. High temperature (0.8-1.0). 32B+ for best results.",
    },
  };

  const getRoleMeta = (role: string) => ROLE_META[role] || {
    accent: COLORS.dim,
    icon: "⚙️",
    label: role.replace(/_/g, " "),
    hint: "Custom worker role. Assign any model.",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          Model Configuration
        </h1>
        {status && <span className="text-green text-xs bp-mono-data">{status}</span>}
      </div>

      {/* Orchestrator (main model) */}
      <PanelCard accent={COLORS.cyan}>
        <div className="flex items-center gap-2 mb-4">
          <Crown size={16} style={{ color: COLORS.cyan }} />
          <span className="text-sm font-semibold text-text" style={{ fontFamily: "var(--font-display)" }}>
            Orchestrator Model
          </span>
          <span className="text-dim text-[10px] ml-1">
            — plans tasks, classifies prompts, routes to workers
          </span>
          {orchDirty && (
            <button onClick={saveOrch}
              className="ml-auto px-3 py-1 text-[11px] flex items-center gap-1 border transition-all"
              style={{ background: "linear-gradient(135deg, #2FFCC822, #2FFCC810)", borderColor: "#2FFCC855", color: COLORS.cyan, borderRadius: 0 }}>
              <Save size={11} /> Save
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-4">
          {/* Provider */}
          <label className="space-y-1.5">
            <span className="bp-label-caps flex items-center gap-1"><Globe size={9} /> Provider</span>
            <div className="flex gap-2">
              <select value={orch.provider}
                onChange={e => { updateOrch("provider", e.target.value); fetchModels(e.target.value); }}
                className="flex-1 bg-surface-0 border border-border text-text text-xs px-2.5 py-2 focus:outline-none focus:border-cyan/40"
                style={{ borderRadius: 0 }}>
                {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <button onClick={() => fetchModels(orch.provider)}
                className="px-2 py-1 border text-dim hover:text-sec transition-all"
                style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", borderRadius: 0 }}
                title="Refresh available models">
                <RefreshCw size={12} className={loadingModels === orch.provider ? "animate-spin" : ""} />
              </button>
            </div>
          </label>

          {/* Model */}
          <label className="space-y-1.5">
            <span className="bp-label-caps flex items-center gap-1"><Cpu size={9} /> Model</span>
            <ModelSelect
              value={orch.model}
              models={orchModels}
              onChange={v => updateOrch("model", v)}
            />
          </label>

          {/* Context Window */}
          <label className="space-y-1.5">
            <span className="bp-label-caps flex items-center gap-1"><Layers size={9} /> Context Window</span>
            <div className="flex items-center gap-3">
              <input type="range" min={2048} max={131072} step={1024}
                value={orch.context_window}
                onChange={e => updateOrch("context_window", +e.target.value)}
                className="flex-1 accent-cyan h-1" />
              <span className="bp-mono-data w-16 text-right text-cyan">
                {(orch.context_window / 1024).toFixed(0)}k
              </span>
            </div>
            <div className="flex justify-between text-dim text-[9px]">
              <span>2k</span><span>128k</span>
            </div>
          </label>

          {/* Endpoint */}
          <label className="space-y-1.5">
            <span className="bp-label-caps">Endpoint</span>
            <input value={orch.endpoint} onChange={e => updateOrch("endpoint", e.target.value)}
              className="w-full bg-surface-0 border border-border text-text text-xs px-2.5 py-2 focus:outline-none focus:border-cyan/40"
              style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}
              placeholder="http://localhost:11434" />
          </label>
        </div>
      </PanelCard>

      {/* Worker Models */}
      <div className="flex items-center gap-2 mt-2">
        <Cpu size={14} className="text-dim" />
        <span className="bp-label-caps text-dim" style={{ fontSize: 10 }}>Worker Model Assignments</span>
      </div>

      <div className="space-y-2">
        {Object.entries(workers).map(([role, cfg]) => {
          const meta = getRoleMeta(role);
          const expanded = expandedWorker === role;
          const wModels = availableModels[cfg.provider] || [];

          return (
            <div key={role}
              className="bp-panel transition-all duration-150"
              style={{ borderLeftColor: meta.accent, borderLeftWidth: 2 }}>

              {/* Collapsed row */}
              <div className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none"
                onClick={() => setExpandedWorker(expanded ? null : role)}>

                <span className="text-base shrink-0" title={meta.label}>{meta.icon}</span>

                <div className="flex flex-col flex-shrink-0 w-36">
                  <span className="text-sm font-medium text-text leading-tight">{meta.label}</span>
                  <span className="text-[9px] text-dim leading-tight">{role}</span>
                </div>

                <span className="bp-mono-data flex-1 truncate">{cfg.model}</span>

                <span className="text-dim text-[10px] w-14">{cfg.provider}</span>

                <span className="bp-mono-data w-10 text-right">{(cfg.context_window / 1024).toFixed(0)}k</span>

                <div className="flex items-center gap-1 text-dim text-[10px] w-12">
                  <Thermometer size={9} /> {cfg.temperature.toFixed(2)}
                </div>

                <StatusBadge status={cfg.enabled ? "active" : "idle"} size="sm" />

                {workerDirty.has(role) && (
                  <button onClick={e => { e.stopPropagation(); saveWorker(role); }}
                    className="px-2 py-0.5 text-[10px] border transition-all"
                    style={{ background: "var(--color-surface-2)", borderColor: "#2FFCC855", color: COLORS.cyan, borderRadius: 0 }}>
                    <Save size={10} />
                  </button>
                )}

                {expanded ? <ChevronUp size={14} className="text-dim" /> : <ChevronDown size={14} className="text-dim" />}
              </div>

              {/* Expanded panel */}
              {expanded && (
                <div className="px-4 pb-4 pt-1 border-t animate-view-enter"
                  style={{ borderColor: "var(--color-border)" }}>

                  <p className="text-dim text-[11px] mb-1">{cfg.description}</p>
                  <p className="text-[10px] mb-3 italic" style={{ color: meta.accent + "aa" }}>
                    {meta.hint}
                  </p>

                  <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                    {/* Provider */}
                    <label className="space-y-1">
                      <span className="bp-label-caps">Provider</span>
                      <div className="flex gap-2">
                        <select value={cfg.provider}
                          onChange={e => { updateWorker(role, "provider", e.target.value); fetchModels(e.target.value); }}
                          className="flex-1 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
                          style={{ borderRadius: 0 }}>
                          {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                        <button onClick={() => fetchModels(cfg.provider)}
                          className="px-1.5 border text-dim hover:text-sec"
                          style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", borderRadius: 0 }}>
                          <RefreshCw size={10} className={loadingModels === cfg.provider ? "animate-spin" : ""} />
                        </button>
                      </div>
                    </label>

                    {/* Model */}
                    <label className="space-y-1">
                      <span className="bp-label-caps">Model</span>
                      <ModelSelect
                        value={cfg.model}
                        models={wModels}
                        onChange={v => updateWorker(role, "model", v)}
                      />
                    </label>

                    {/* Context Window */}
                    <label className="space-y-1">
                      <span className="bp-label-caps">Context Window</span>
                      <div className="flex items-center gap-2">
                        <input type="range" min={2048} max={131072} step={1024}
                          value={cfg.context_window}
                          onChange={e => updateWorker(role, "context_window", +e.target.value)}
                          className="flex-1 accent-cyan h-1" />
                        <span className="bp-mono-data w-12 text-right">{(cfg.context_window / 1024).toFixed(0)}k</span>
                      </div>
                    </label>

                    {/* Temperature */}
                    <label className="space-y-1">
                      <span className="bp-label-caps">Temperature</span>
                      <div className="flex items-center gap-2">
                        <input type="range" min={0} max={1} step={0.05}
                          value={cfg.temperature}
                          onChange={e => updateWorker(role, "temperature", +e.target.value)}
                          className="flex-1 accent-cyan h-1" />
                        <span className="bp-mono-data w-10 text-right">{cfg.temperature.toFixed(2)}</span>
                      </div>
                    </label>
                  </div>

                  <label className="flex items-center gap-2 mt-3 cursor-pointer">
                    <input type="checkbox" checked={cfg.enabled}
                      onChange={e => updateWorker(role, "enabled", e.target.checked)}
                      className="accent-cyan" />
                    <span className="text-dim text-xs">Enabled for task routing</span>
                  </label>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
