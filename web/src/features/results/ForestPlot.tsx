import { motion, useReducedMotion } from "motion/react";
import type { EvalSummary } from "../../shared/api/types";
import { color, motionTiming, plot } from "../../shared/theme/tokens";
import { metricName, pct, scale } from "../../shared/ui/format";

const LABEL_W = 170;
const PAD = 12;

/** One row per agent: the point estimate and its 95% interval on a 0–100 % axis. */
export function ForestPlot({
  rows,
  metric,
  higherIsBetter,
}: { rows: EvalSummary[]; metric: string; higherIsBetter: boolean }) {
  const reduce = useReducedMotion();
  const w = plot.width;
  const h = plot.rowHeight * rows.length + 28;
  return (
    <svg
      viewBox={`0 0 ${LABEL_W + w + PAD * 4} ${h}`}
      width="100%"
      role="img"
      aria-label={`${metricName(metric)} by agent with 95% intervals; ${higherIsBetter ? "higher" : "lower"} is better`}
    >
      {plot.axisTicks.map((t) => (
        <g key={t} transform={`translate(${LABEL_W + PAD + scale(t, w)},0)`}>
          <line y1={0} y2={h - 22} stroke={color.rule} />
          <text y={h - 6} textAnchor="middle" fontSize={11} fill={color.inkMuted}>
            {t * 100} %
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const m = r.metrics[metric];
        const y = i * plot.rowHeight + plot.rowHeight / 2;
        const x = (v: number) => LABEL_W + PAD + scale(v, w);
        return (
          <g key={r.agent}>
            <text x={0} y={y + 4} fontSize={13} fill={color.ink}>
              {r.agent}
            </text>
            {m?.value === null || m === undefined ? (
              <text x={LABEL_W + PAD} y={y + 4} fontSize={12} fill={color.inkMuted}>
                no cases
              </text>
            ) : (
              <>
                <motion.line
                  x1={x(m.low ?? m.value)}
                  x2={x(m.high ?? m.value)}
                  y1={y}
                  y2={y}
                  stroke={color.ink}
                  strokeWidth={2}
                  initial={reduce ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ ...motionTiming.enter, delay: i * motionTiming.stagger }}
                />
                <motion.circle
                  cy={y}
                  r={plot.dot}
                  fill={color.accent}
                  initial={reduce ? false : { cx: x(0) }}
                  animate={{ cx: x(m.value) }}
                  transition={{ ...motionTiming.enter, delay: i * motionTiming.stagger }}
                >
                  <title>{`${r.agent}: ${pct(m.value)} (${pct(m.low)} – ${pct(m.high)}), ${m.k} of ${m.n}`}</title>
                </motion.circle>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
