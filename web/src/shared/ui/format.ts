export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return `${(v * 100).toFixed(digits)} %`;
}

export function signedPts(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  const pts = v * 100;
  const sign = pts > 0 ? "+" : pts < 0 ? "−" : "±";
  return `${sign}${Math.abs(pts).toFixed(1)} pts`;
}

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return v < 0.01 && v > 0 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
}

/** Position on a 0..1 scale as a share of a width, clamped so a dot never leaves the axis. */
export function scale(v: number, width: number): number {
  return Math.min(width, Math.max(0, v * width));
}

export const METRIC_NAMES: Record<string, string> = {
  recall: "Recall",
  precision: "Precision",
  recall_digital: "Recall, text documents",
  recall_scanned: "Recall, scanned documents",
  clean_false_alarm_rate: "Clean packages with a wrong flag",
  decoy_false_alarm_rate: "Restatements flagged as errors",
};

export function metricName(key: string): string {
  if (METRIC_NAMES[key]) return METRIC_NAMES[key];
  const [m, kind] = key.split(":");
  return kind ? `${METRIC_NAMES[m] ?? m}: ${kind.replace("_", " ")}` : key;
}
