import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../../shared/api/client";
import type { EvalSummary } from "../../shared/api/types";
import { Async, EmptyState } from "../../shared/ui/States";
import { Tickmark, VERDICT_ORDER } from "../../shared/ui/Tickmark";
import { metricName, pct, usd } from "../../shared/ui/format";
import { ForestPlot } from "./ForestPlot";

const METRICS = [
  { key: "recall", better: "higher" },
  { key: "precision", better: "higher" },
  { key: "recall_scanned", better: "higher" },
  { key: "recall_digital", better: "higher" },
  { key: "clean_false_alarm_rate", better: "lower" },
  { key: "decoy_false_alarm_rate", better: "lower" },
] as const;

const KINDS = ["casting", "tie", "prior_year", "narrative", "missing_disclosure", "period"];

function preferredSplit(rows: EvalSummary[]): string {
  const counts = new Map<string, number>();
  for (const r of rows) counts.set(r.split, (counts.get(r.split) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0];
}

function Results({ rows }: { rows: EvalSummary[] }) {
  const splits = useMemo(() => [...new Set(rows.map((r) => r.split))].sort(), [rows]);
  const [split, setSplit] = useState(() => preferredSplit(rows));
  const [metric, setMetric] = useState<string>("recall");
  const shown = rows.filter((r) => r.split === split);
  const better = METRICS.find((m) => m.key === metric)?.better ?? "higher";
  const first = shown[0];
  return (
    <>
      <div className="tabs" aria-label="Dataset split">
        {splits.map((s) => (
          <button key={s} type="button" aria-pressed={s === split} onClick={() => setSplit(s)}>
            {s} split
          </button>
        ))}
      </div>
      <p className="lede">
        {first?.packages} packages, {first?.defects} seeded errors. Intervals come from resampling whole
        packages.
      </p>
      <section className="panel" aria-labelledby="plot-h">
        <h2 id="plot-h">{metricName(metric)}</h2>
        <div className="tabs" aria-label="Metric">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              aria-pressed={m.key === metric}
              onClick={() => setMetric(m.key)}
            >
              {metricName(m.key)}
            </button>
          ))}
        </div>
        <ForestPlot rows={shown} metric={metric} higherIsBetter={better === "higher"} />
      </section>

      <h2>Recall by kind of error</h2>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th scope="col">Agent</th>
              {KINDS.map((k) => (
                <th key={k} scope="col" className="num">
                  {k.replace("_", " ")}
                </th>
              ))}
              <th scope="col" className="num">
                Cost / package
              </th>
              <th scope="col" className="num">
                p95 time
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.agent}>
                <th scope="row">{r.agent}</th>
                {KINDS.map((k) => {
                  const m = r.metrics[`recall:${k}`];
                  return (
                    <td key={k} className="num" title={m ? `${m.k} of ${m.n}` : undefined}>
                      {pct(m?.value, 0)}
                    </td>
                  );
                })}
                <td className="num">{usd(r.operational.cost_per_package_usd)}</td>
                <td className="num">{r.operational.p95_latency_s?.toFixed(1)} s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>What the findings were</h2>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th scope="col">Verdict</th>
              {shown.map((r) => (
                <th key={r.agent} scope="col" className="num">
                  {r.agent}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {VERDICT_ORDER.map((v) => (
              <tr key={v}>
                <th scope="row">
                  <Tickmark verdict={v} />
                </th>
                {shown.map((r) => (
                  <td key={r.agent} className="num">
                    {r.verdicts[v] ?? 0}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ResultsScreen() {
  const q = useQuery({ queryKey: ["evals"], queryFn: api.evals });
  return (
    <>
      <h1>Results</h1>
      <p className="lede">
        How often each review agent finds the seeded errors, and how often its flags are right.
      </p>
      <Async
        q={q}
        what="results"
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No evaluation has been run yet.">
            <p>
              Run <code>aae eval baseline --split dev</code> to score the rules agent; results appear here.
            </p>
          </EmptyState>
        }
      >
        {(rows) => <Results rows={rows} />}
      </Async>
    </>
  );
}
