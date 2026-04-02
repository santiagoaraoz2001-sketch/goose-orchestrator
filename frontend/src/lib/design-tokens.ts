/* Blueprint Design Tokens — Specific Labs */

export const COLORS = {
  bg: "#060709",
  bgAlt: "#090C11",
  text: "#F2F4F8",
  sec: "#C4CDDE",
  dim: "#90A0B5",
  muted: "#1A1F2C",
  surface0: "#0B0D13",
  surface1: "#0F1319",
  surface2: "#141922",
  surface3: "#1B2130",
  surface4: "#222A3C",
  surface5: "#2C3649",
  surface6: "#384557",
  border: "#252E3C",
  borderHi: "#374659",
  cyan: "#2FFCC8",
  green: "#3EF07A",
  amber: "#FFBE45",
  red: "#FF5E72",
  blue: "#5B96FF",
  purple: "#A87EFF",
  pink: "#F070C8",
  teal: "#35D8F0",
} as const;

export const STATUS_COLORS: Record<string, string> = {
  planning: COLORS.amber,
  active: COLORS.cyan,
  complete: COLORS.green,
  failed: COLORS.red,
  pending: COLORS.dim,
  idle: COLORS.dim,
};

export const MOTION = {
  fast: "0.16s",
  base: "0.24s",
  slow: "0.38s",
} as const;
