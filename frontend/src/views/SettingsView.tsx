import { useState, useEffect, useCallback } from "react";
import { Save } from "lucide-react";
import { PanelCard } from "@/components/shared/PanelCard";
import { apiGet, apiPatch } from "@/api/client";

export default function SettingsView() {
  const [config, setConfig] = useState<any>(null);
  const [orchDirty, setOrchDirty] = useState(false);
  const [resDirty, setResDirty] = useState(false);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    const data = await apiGet("/api/config");
    setConfig(data);
    setOrchDirty(false);
    setResDirty(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!config) return <div className="text-dim">Loading...</div>;

  const orch = config.orchestrator || {};
  const res = config.resources || {};
  const prov = config.providers || {};

  const updateOrch = (field: string, value: any) => {
    setConfig((prev: any) => ({ ...prev, orchestrator: { ...prev.orchestrator, [field]: value } }));
    setOrchDirty(true);
  };

  const updateRes = (field: string, value: any) => {
    setConfig((prev: any) => ({ ...prev, resources: { ...prev.resources, [field]: value } }));
    setResDirty(true);
  };

  const saveOrch = async () => {
    await apiPatch("/api/config/orchestrator", config.orchestrator);
    setOrchDirty(false);
    setStatus("Orchestrator saved");
    setTimeout(() => setStatus(""), 2000);
  };

  const saveRes = async () => {
    await apiPatch("/api/config/resources", config.resources);
    setResDirty(false);
    setStatus("Resources saved");
    setTimeout(() => setStatus(""), 2000);
  };

  const saveProv = async (name: string) => {
    await apiPatch(`/api/config/providers/${name}`, prov[name]);
    setStatus(`Provider ${name} saved`);
    setTimeout(() => setStatus(""), 2000);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          Settings
        </h1>
        {status && <span className="text-green text-xs bp-mono-data">{status}</span>}
      </div>

      {/* Orchestrator Model */}
      <PanelCard title="Orchestrator Model" accent="var(--color-cyan)">
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <span className="bp-label-caps">Model</span>
            <input value={orch.model || ""} onChange={e => updateOrch("model", e.target.value)}
              className="w-full bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
              style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }} />
          </label>
          <label className="space-y-1">
            <span className="bp-label-caps">Provider</span>
            <select value={orch.provider || "ollama"} onChange={e => updateOrch("provider", e.target.value)}
              className="w-full bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none"
              style={{ borderRadius: 0 }}>
              <option value="ollama">Ollama</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="bp-label-caps">Context Window</span>
            <div className="flex items-center gap-2">
              <input type="range" min={2048} max={131072} step={1024}
                value={orch.context_window || 32768}
                onChange={e => updateOrch("context_window", +e.target.value)}
                className="flex-1 accent-cyan" />
              <span className="bp-mono-data w-14 text-right">{((orch.context_window || 32768) / 1024).toFixed(0)}k</span>
            </div>
          </label>
          <label className="space-y-1">
            <span className="bp-label-caps">Endpoint</span>
            <input value={orch.endpoint || ""} onChange={e => updateOrch("endpoint", e.target.value)}
              className="w-full bg-surface-0 border border-border text-text text-xs px-2 py-1.5 focus:outline-none focus:border-cyan/40"
              style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }} />
          </label>
        </div>
        {orchDirty && (
          <button onClick={saveOrch}
            className="mt-3 px-4 py-1.5 text-xs flex items-center gap-1 border"
            style={{ background: "linear-gradient(135deg, #2FFCC822, #2FFCC810)", borderColor: "#2FFCC855", color: "var(--color-cyan)", borderRadius: 0 }}>
            <Save size={12} /> Save
          </button>
        )}
      </PanelCard>

      {/* Resource Limits */}
      <PanelCard title="Resource Limits" accent="var(--color-amber)">
        <div className="grid grid-cols-3 gap-4">
          <label className="space-y-1">
            <span className="bp-label-caps">Max Workers</span>
            <div className="flex items-center gap-2">
              <input type="range" min={1} max={8} step={1}
                value={res.max_simultaneous_workers || 2}
                onChange={e => updateRes("max_simultaneous_workers", +e.target.value)}
                className="flex-1 accent-cyan" />
              <span className="bp-mono-data w-6 text-right">{res.max_simultaneous_workers || 2}</span>
            </div>
          </label>
          <label className="space-y-1">
            <span className="bp-label-caps">VRAM Budget (GB)</span>
            <div className="flex items-center gap-2">
              <input type="range" min={8} max={256} step={4}
                value={res.vram_budget_gb || 180}
                onChange={e => updateRes("vram_budget_gb", +e.target.value)}
                className="flex-1 accent-cyan" />
              <span className="bp-mono-data w-10 text-right">{res.vram_budget_gb || 180}</span>
            </div>
          </label>
          <label className="space-y-1">
            <span className="bp-label-caps">API Rate (rpm)</span>
            <div className="flex items-center gap-2">
              <input type="range" min={10} max={300} step={10}
                value={res.api_rate_limit_rpm || 60}
                onChange={e => updateRes("api_rate_limit_rpm", +e.target.value)}
                className="flex-1 accent-cyan" />
              <span className="bp-mono-data w-10 text-right">{res.api_rate_limit_rpm || 60}</span>
            </div>
          </label>
        </div>
        {resDirty && (
          <button onClick={saveRes}
            className="mt-3 px-4 py-1.5 text-xs flex items-center gap-1 border"
            style={{ background: "linear-gradient(135deg, #2FFCC822, #2FFCC810)", borderColor: "#2FFCC855", color: "var(--color-cyan)", borderRadius: 0 }}>
            <Save size={12} /> Save
          </button>
        )}
      </PanelCard>

      {/* Providers */}
      <PanelCard title="Provider Endpoints" accent="var(--color-purple)">
        <div className="space-y-3">
          {Object.entries(prov).map(([name, p]: [string, any]) => (
            <div key={name} className="flex items-end gap-3 p-3 border"
                 style={{ background: "var(--color-surface-0)", borderColor: "var(--color-border)" }}>
              <div className="w-24">
                <span className="bp-label-caps">{name}</span>
              </div>
              <label className="flex-1 space-y-1">
                <span className="text-dim text-[10px]">Endpoint</span>
                <input value={p.endpoint || ""} onChange={e => {
                  setConfig((prev: any) => ({
                    ...prev,
                    providers: { ...prev.providers, [name]: { ...prev.providers[name], endpoint: e.target.value } }
                  }));
                }}
                  className="w-full bg-surface-1 border border-border text-text text-xs px-2 py-1 focus:outline-none focus:border-cyan/40"
                  style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }} />
              </label>
              <label className="w-40 space-y-1">
                <span className="text-dim text-[10px]">API Key Env</span>
                <input value={p.api_key_env || ""} onChange={e => {
                  setConfig((prev: any) => ({
                    ...prev,
                    providers: { ...prev.providers, [name]: { ...prev.providers[name], api_key_env: e.target.value } }
                  }));
                }}
                  className="w-full bg-surface-1 border border-border text-text text-xs px-2 py-1 focus:outline-none focus:border-cyan/40"
                  style={{ borderRadius: 0, fontFamily: "var(--font-mono)" }} />
              </label>
              <button onClick={() => saveProv(name)}
                className="px-2 py-1 border text-[10px]"
                style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-cyan)", borderRadius: 0 }}>
                <Save size={10} />
              </button>
            </div>
          ))}
        </div>
      </PanelCard>
    </div>
  );
}
