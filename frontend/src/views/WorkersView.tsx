import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Save, RefreshCw } from "lucide-react";
import { PanelCard } from "@/components/shared/PanelCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { apiGet, apiPatch, apiPost, apiDelete } from "@/api/client";
import { COLORS } from "@/lib/design-tokens";

interface WorkerCfg {
  model: string;
  provider: string;
  context_window: number;
  temperature: number;
  enabled: boolean;
  description: string;
  tools?: string[];
}

const ROLE_COLORS: Record<string, string> = {
  deep_research: COLORS.blue,
  local_rag: COLORS.teal,
  code_gen: COLORS.cyan,
  summarizer: COLORS.amber,
  math_reasoning: COLORS.purple,
  creative: COLORS.pink,
};

export default function WorkersView() {
  const [workers, setWorkers] = useState<Record<string, WorkerCfg>>({});
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [newRole, setNewRole] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});

  const fetchModels = async (provider: string) => {
    try {
      const data = await apiGet(`/api/models/${provider}`);
      setAvailableModels(prev => ({ ...prev, [provider]: data.models || [] }));
    } catch {
      setAvailableModels(prev => ({ ...prev, [provider]: [] }));
    }
  };

  const load = useCallback(async () => {
    const data = await apiGet("/api/config/workers");
    setWorkers(data);
    setDirty(new Set());

    // Auto-fetch models for all providers in use
    const providers = new Set<string>();
    for (const w of Object.values(data)) {
      if ((w as any).provider) providers.add((w as any).provider);
    }
    for (const p of providers) fetchModels(p);
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = (role: string, field: string, value: any) => {
    setWorkers(prev => ({
      ...prev,
      [role]: { ...prev[role], [field]: value },
    }));
    setDirty(prev => new Set(prev).add(role));
  };

  const save = async (role: string) => {
    setSaving(role);
    try {
      await apiPatch(`/api/config/workers/${role}`, workers[role]);
      setDirty(prev => { const n = new Set(prev); n.delete(role); return n; });
    } catch (e: any) {
      alert(e.message);
    }
    setSaving(null);
  };

  const remove = async (role: string) => {
    if (!confirm(`Remove worker role "${role}"?`)) return;
    await apiDelete(`/api/config/workers/${role}`);
    load();
  };

  const add = async () => {
    const name = newRole.trim().toLowerCase().replace(/\s+/g, "_");
    if (!name) return;
    await apiPost(`/api/config/workers/${name}`, {
      model: "qwen3:8b", provider: "ollama", context_window: 16384,
      temperature: 0.7, enabled: true, description: `Custom role: ${name}`,
    });
    setNewRole("");
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          Worker Roles
        </h1>
        <div className="flex gap-2">
          <input
            value={newRole}
            onChange={e => setNewRole(e.target.value)}
            onKeyDown={e => e.key === "Enter" && add()}
            placeholder="New role name..."
            className="bg-surface-0 border border-border text-text text-xs px-3 py-1.5 w-48 focus:outline-none focus:border-cyan/40"
            style={{ borderRadius: 0 }}
          />
          <button onClick={add} disabled={!newRole.trim()}
            className="px-3 py-1.5 text-xs flex items-center gap-1 border transition-all disabled:opacity-30"
            style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-cyan)", borderRadius: 0 }}>
            <Plus size={12} /> Add
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Object.entries(workers).map(([role, cfg]) => (
          <PanelCard key={role} accent={ROLE_COLORS[role] || COLORS.dim}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text">{role.replace(/_/g, " ")}</span>
                <StatusBadge status={cfg.enabled ? "active" : "idle"} size="sm" />
              </div>
              <div className="flex gap-1">
                {dirty.has(role) && (
                  <button onClick={() => save(role)}
                    className="p-1.5 border transition-all hover:border-cyan/40"
                    style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-cyan)", borderRadius: 0 }}>
                    <Save size={12} />
                  </button>
                )}
                <button onClick={() => remove(role)}
                  className="p-1.5 border transition-all hover:border-red/40"
                  style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-red)", borderRadius: 0 }}>
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            <p className="text-dim text-[11px] mb-3">{cfg.description}</p>

            <div className="grid grid-cols-2 gap-3">
              {/* Model */}
              <label className="space-y-1">
                <span className="bp-label-caps">Model</span>
                {(() => {
                  const models = availableModels[cfg.provider] || [];
                  const inList = models.includes(cfg.model);
                  return models.length > 0 ? (
                    <div className="flex gap-1">
                      <select value={inList ? cfg.model : "__other__"}
                        onChange={e => {
                          if (e.target.value !== "__other__") update(role, "model", e.target.value);
                        }}
                        className="flex-1 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
                        style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}>
                        {!inList && cfg.model && <option value="__other__">{cfg.model} (current)</option>}
                        {models.map(m => <option key={m} value={m}>{m}</option>)}
                        <option value="__other__">— custom —</option>
                      </select>
                      {!inList && (
                        <input value={cfg.model} onChange={e => update(role, "model", e.target.value)}
                          className="w-32 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
                          style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}
                          placeholder="model:tag" />
                      )}
                    </div>
                  ) : (
                    <div className="flex gap-1">
                      <input value={cfg.model} onChange={e => update(role, "model", e.target.value)}
                        className="flex-1 bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
                        style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }}
                        placeholder="model:tag" />
                      <button onClick={() => fetchModels(cfg.provider)}
                        className="px-1.5 border text-dim hover:text-sec shrink-0"
                        style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", borderRadius: 0 }}
                        title="Load available models">
                        <RefreshCw size={10} />
                      </button>
                    </div>
                  );
                })()}
              </label>
              {/* Provider */}
              <label className="space-y-1">
                <span className="bp-label-caps">Provider</span>
                <select value={cfg.provider} onChange={e => { update(role, "provider", e.target.value); fetchModels(e.target.value); }}
                  className="w-full bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
                  style={{ borderRadius: 0 }}>
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </label>
              {/* Context Window */}
              <label className="space-y-1">
                <span className="bp-label-caps">Context Window</span>
                <div className="flex items-center gap-2">
                  <input type="range" min={2048} max={131072} step={1024}
                    value={cfg.context_window} onChange={e => update(role, "context_window", +e.target.value)}
                    className="flex-1 accent-cyan" />
                  <span className="bp-mono-data w-14 text-right">{(cfg.context_window / 1024).toFixed(0)}k</span>
                </div>
              </label>
              {/* Temperature */}
              <label className="space-y-1">
                <span className="bp-label-caps">Temperature</span>
                <div className="flex items-center gap-2">
                  <input type="range" min={0} max={1} step={0.05}
                    value={cfg.temperature} onChange={e => update(role, "temperature", +e.target.value)}
                    className="flex-1 accent-cyan" />
                  <span className="bp-mono-data w-8 text-right">{cfg.temperature.toFixed(2)}</span>
                </div>
              </label>
            </div>

            {/* Enable toggle */}
            <label className="flex items-center gap-2 mt-3 cursor-pointer">
              <input type="checkbox" checked={cfg.enabled}
                onChange={e => update(role, "enabled", e.target.checked)}
                className="accent-cyan" />
              <span className="text-dim text-xs">Enabled</span>
            </label>
          </PanelCard>
        ))}
      </div>
    </div>
  );
}
