import { ReactNode, CSSProperties } from "react";

interface Props {
  title?: string;
  accent?: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
}

export function PanelCard({ title, accent = "var(--color-cyan)", children, className = "", style, onClick }: Props) {
  return (
    <div
      className={`bp-panel p-4 transition-all duration-150 ${onClick ? "cursor-pointer" : ""} ${className}`}
      style={style}
      onClick={onClick}
    >
      {/* Top accent bar */}
      <div className="absolute top-0 left-4 right-4 h-[1px]"
           style={{ background: `linear-gradient(90deg, transparent 0%, ${accent}44 50%, transparent 100%)` }} />

      {title && (
        <div className="bp-label-caps mb-3" style={{ color: accent }}>{title}</div>
      )}
      {children}
    </div>
  );
}
