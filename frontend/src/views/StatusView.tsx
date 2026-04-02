import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Trash2, HardDrive, Cpu } from "lucide-react";
import { PanelCard } from "@/components/shared/PanelCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { apiGet, apiPost } from "@/api/client";
import { COLORS } from "@/lib/design-tokens";

interface LoadedModel {
  model: string;
  provider: string;
  vram_gb: number;
  is_orchestrator: boolean;
  idle_seconds: number;
}

export default function StatusView() {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet("/api/status");
      setStatus(data);
    } catch (e: any) {
      setStatus({ error: e.message });
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, [load]);

  const resetAll = async () => {
    await apiPost("/api/reset", {});
    load();
  };

  if (!status) return <div className="text-dim">Loading...</div>;
  if (status.error) return <div className="text-red">Error: {status.error}</div>;

  const budget = status.vram_budget_gb || 0;
  const used = status.used_vram_gb || 0;
  const available = status.available_vram_gb || 0;
  const pct = budget > 0 ? (used / budget) * 100 : 0;
  const models: LoadedModel[] = status.loaded_models || [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
          Model Pool Status
        </h1>
        <div className="flex gap-2">
          <button onClick={load}
            className="px-3 py-1.5 text-xs flex items-center gap-1 border transition-all"
            style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-sec)", borderRadius: 0 }}>
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
          <button onClick={resetAll}
            className="px-3 py-1.5 text-xs flex items-center gap-1 border transition-all hover:border-red/40"
            style={{ background: "var(--color-surface-2)", borderColor: "var(--color-border)", color: "var(--color-red)", borderRadius: 0 }}>
            <Trash2 size={12} /> Unload All
          </button>
        </div>
      </div>

      {/* VRAM budget bar */}
      <PanelCard title="Memory" accent="var(--color-cyan)">
        <div className="flex items-center gap-4 mb-2">
          <HardDrive size={16} className="text-cyan" />
          <div className="flex-1">
            <div className="flex justify-between mb-1">
              <span className="bp-mono-data">{used.toFixed(1)} GB used</span>
              <span className="bp-mono-data">{available.toFixed(1)} GB free / {budget} GB total</span>
            </div>
            <div className="h-2 w-full" style={{ background: "var(--color-surface-0)", border: "1px solid var(--color-border)" }}>
              <div className="h-full transition-all duration-500"
                   style={{
                     width: `${Math.min(pct, 100)}%`,
                     background: pct > 90 ? COLORS.red : pct > 70 ? COLORS.amber : COLORS.cyan,
                   }} />
            </div>
          </div>
        </div>
      </PanelCard>

      {/* Loaded models */}
      {models.length === 0 ? (
        <PanelCard>
          <p className="text-dim text-sm text-center py-6">No models loaded</p>
        </PanelCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {models.map((m) => (
            <PanelCard key={m.model} accent={m.is_orchestrator ? COLORS.cyan : COLORS.purple}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Cpu size={14} style={{ color: m.is_orchestrator ? COLORS.cyan : COLORS.purple }} />
                  <span className="text-sm font-semibold text-text" style={{ fontFamily: "var(--font-mono)" }}>
                    {m.model}
                  </span>
                </div>
                <StatusBadge status={m.is_orchestrator ? "active" : "idle"} />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <span className="bp-label-caps">Provider</span>
                  <p className="bp-mono-data">{m.provider}</p>
                </div>
                <div>
                  <span className="bp-label-caps">VRAM</span>
                  <p className="bp-mono-data">{m.vram_gb.toFixed(1)} GB</p>
                </div>
                <div>
                  <span className="bp-label-caps">Idle</span>
                  <p className="bp-mono-data">{m.idle_seconds.toFixed(0)}s</p>
                </div>
              </div>
              {m.is_orchestrator && (
                <div className="mt-2 text-[10px] text-cyan/60">Pinned — will not be evicted</div>
              )}
            </PanelCard>
          ))}
        </div>
      )}
    </div>
  );
}
