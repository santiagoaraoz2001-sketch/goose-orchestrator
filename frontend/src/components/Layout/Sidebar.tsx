import { NavLink } from "react-router-dom";
import {
  Zap,
  Users,
  Settings,
  Activity,
  Box,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Dashboard", icon: Zap },
  { to: "/models", label: "Models", icon: Box },
  { to: "/workers", label: "Workers", icon: Users },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/status", label: "Status", icon: Activity },
];

export function Sidebar() {
  return (
    <aside className="w-[200px] shrink-0 flex flex-col border-r"
           style={{
             background: "linear-gradient(180deg, var(--color-surface-1) 0%, var(--color-surface-0) 100%)",
             borderColor: "var(--color-border)",
           }}>
      {/* Logo */}
      <div className="h-[46px] flex items-center px-4 gap-2 border-b"
           style={{ borderColor: "var(--color-border)" }}>
        <div className="w-2.5 h-2.5 rounded-full"
             style={{ background: "var(--color-cyan)", boxShadow: "0 0 8px var(--color-cyan)" }} />
        <span className="text-sm font-semibold text-text" style={{ fontFamily: "var(--font-display)" }}>
          Orchestrator
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 flex flex-col gap-0.5">
        <div className="bp-label-caps px-3 mb-2">Navigation</div>
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 text-[12px] rounded-none relative transition-all duration-150 ${
                isActive
                  ? "text-cyan"
                  : "text-dim hover:text-sec hover:bg-surface-3/50"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div className="absolute left-0 top-1 bottom-1 w-[2.5px] rounded-r"
                       style={{ background: "var(--color-cyan)", boxShadow: "0 0 6px var(--color-cyan)" }} />
                )}
                <Icon size={14} strokeWidth={1.8} />
                <span className="font-medium">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t text-dim text-[10px]"
           style={{ borderColor: "var(--color-border)", fontFamily: "var(--font-mono)" }}>
        v0.2.0
      </div>
    </aside>
  );
}
