import { useState, useRef, useCallback, useEffect } from "react";
import { Send, Loader2, CheckCircle, XCircle, Clock } from "lucide-react";
import { PanelCard } from "@/components/shared/PanelCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { createWs, WsEvent } from "@/api/client";

interface StepEvent {
  step_id: number;
  role: string;
  model?: string;
  status: string;
  text?: string;
  error?: string;
  elapsed_s?: number;
}

export default function DashboardView() {
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [output, setOutput] = useState("");
  const [stats, setStats] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const handleSubmit = useCallback(() => {
    if (!prompt.trim() || running) return;
    setRunning(true);
    setPlan(null);
    setSteps([]);
    setOutput("");
    setStats(null);

    const ws = createWs((ev: WsEvent) => {
      switch (ev.type) {
        case "plan":
          setPlan(ev);
          // Set all steps as pending initially
          setSteps(ev.steps.map((s: any) => ({
            step_id: s.id, role: s.role, status: "pending",
          })));
          break;
        case "step_result":
          setSteps(prev => prev.map(s =>
            s.step_id === ev.step_id
              ? { ...s, status: ev.success ? "complete" : "failed", text: ev.text, error: ev.error, model: ev.model, elapsed_s: ev.elapsed_s }
              : s
          ));
          break;
        case "complete":
          setOutput(ev.full_output || "");
          setStats({ time: ev.total_time_s, succeeded: ev.succeeded, failed: ev.failed });
          setRunning(false);
          ws.close();
          break;
        case "error":
          setOutput(`Error: ${ev.message}`);
          setRunning(false);
          ws.close();
          break;
        case "status":
          // Update active steps
          setSteps(prev => {
            const active = prev.filter(s => s.status === "pending");
            if (active.length > 0) {
              return prev.map(s => s.step_id === active[0].step_id ? { ...s, status: "active" } : s);
            }
            return prev;
          });
          break;
      }
    });

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "orchestrate", prompt }));
    };
    ws.onerror = () => { setRunning(false); };
    wsRef.current = ws;
  }, [prompt, running]);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
        Dashboard
      </h1>

      {/* Prompt input */}
      <PanelCard>
        <div className="flex gap-3">
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && e.metaKey) handleSubmit(); }}
            placeholder="Describe your task... (⌘+Enter to submit)"
            className="flex-1 bg-surface-0 border border-border text-text placeholder:text-dim p-3 text-sm resize-none focus:outline-none focus:border-cyan/40 transition-colors"
            rows={3}
            style={{ fontFamily: "var(--font-sans)", borderRadius: 0 }}
          />
          <button
            onClick={handleSubmit}
            disabled={running || !prompt.trim()}
            className="self-end px-5 py-2.5 text-sm font-medium flex items-center gap-2 transition-all duration-150 disabled:opacity-30"
            style={{
              background: running ? "var(--color-surface-3)" : "linear-gradient(135deg, #2FFCC822 0%, #2FFCC810 100%)",
              border: "1px solid",
              borderColor: running ? "var(--color-border)" : "#2FFCC855",
              color: running ? "var(--color-dim)" : "var(--color-cyan)",
              borderRadius: 0,
            }}
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {running ? "Running..." : "Orchestrate"}
          </button>
        </div>
      </PanelCard>

      {/* Plan summary */}
      {plan && (
        <PanelCard title="Execution Plan" accent="var(--color-amber)">
          <p className="text-sec text-sm mb-2">{plan.summary}</p>
          <p className="bp-mono-data">{plan.steps.length} steps · planned in {plan.plan_time_s}s</p>
        </PanelCard>
      )}

      {/* Step cards */}
      {steps.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {steps.map(step => (
            <PanelCard
              key={step.step_id}
              accent={step.status === "complete" ? "var(--color-green)" : step.status === "failed" ? "var(--color-red)" : step.status === "active" ? "var(--color-cyan)" : "var(--color-border)"}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-text">
                  Step {step.step_id}: {step.role.replace(/_/g, " ")}
                </span>
                <StatusBadge status={step.status} />
              </div>
              {step.model && (
                <p className="bp-mono-data mb-1">{step.model}</p>
              )}
              {step.elapsed_s != null && (
                <div className="flex items-center gap-1 text-dim text-[10px]">
                  <Clock size={10} /> {step.elapsed_s}s
                </div>
              )}
              {step.text && (
                <div className="mt-2 p-2 text-[11px] text-sec max-h-[120px] overflow-y-auto"
                     style={{ background: "var(--color-surface-0)", border: "1px solid var(--color-border)", fontFamily: "var(--font-mono)" }}>
                  {step.text.slice(0, 500)}{step.text.length > 500 ? "…" : ""}
                </div>
              )}
              {step.error && (
                <p className="mt-2 text-[11px] text-red">{step.error}</p>
              )}
            </PanelCard>
          ))}
        </div>
      )}

      {/* Final output */}
      {output && (
        <PanelCard title="Output" accent="var(--color-green)">
          {stats && (
            <div className="flex gap-4 mb-3 bp-mono-data">
              <span className="text-green">{stats.succeeded} succeeded</span>
              {stats.failed > 0 && <span className="text-red">{stats.failed} failed</span>}
              <span className="text-dim">{stats.time}s total</span>
            </div>
          )}
          <div className="p-3 text-sm text-sec max-h-[400px] overflow-y-auto whitespace-pre-wrap"
               style={{ background: "var(--color-surface-0)", border: "1px solid var(--color-border)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
            {output}
          </div>
        </PanelCard>
      )}
    </div>
  );
}
