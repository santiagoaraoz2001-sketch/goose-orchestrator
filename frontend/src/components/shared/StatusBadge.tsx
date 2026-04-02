import { STATUS_COLORS } from "@/lib/design-tokens";

interface Props {
  status: string;
  size?: "sm" | "md";
}

export function StatusBadge({ status, size = "sm" }: Props) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const sizeClass = size === "sm" ? "text-[9px] px-1.5 py-0.5" : "text-[11px] px-2 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1 font-medium rounded-sm ${sizeClass}`}
      style={{
        background: `${color}14`,
        border: `1px solid ${color}33`,
        color,
      }}
    >
      <span className="w-1 h-1 rounded-full" style={{ background: color }} />
      {status}
    </span>
  );
}
