export function TopBar() {
  return (
    <header className="h-[46px] flex items-center px-5 shrink-0 relative"
            style={{
              background: "linear-gradient(180deg, var(--color-surface-3) 0%, var(--color-surface-1) 100%)",
              borderBottom: "1px solid var(--color-border)",
            }}>
      {/* Cyan accent line */}
      <div className="absolute top-0 left-0 right-0 h-[1px]"
           style={{
             background: "linear-gradient(90deg, transparent 0%, var(--color-cyan) 50%, transparent 100%)",
             opacity: 0.6,
           }} />

      <span className="text-dim text-xs tracking-wide" style={{ fontFamily: "var(--font-mono)" }}>
        goose-orchestrator
      </span>
      <span className="ml-auto text-dim text-xs">by Specific Labs</span>
    </header>
  );
}
