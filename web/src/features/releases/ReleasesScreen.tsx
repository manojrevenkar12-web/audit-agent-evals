import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import type { Release } from "../../shared/api/types";
import { Async, EmptyState } from "../../shared/ui/States";
import { metricName, pct, signedPts } from "../../shared/ui/format";

function Decision({ r }: { r: Release }) {
  return (
    <section
      className="panel"
      aria-labelledby={`rel-${r.candidate}`}
      style={{ marginBottom: "var(--space-lg)" }}
    >
      <h2 id={`rel-${r.candidate}`} style={{ marginTop: 0 }}>
        {r.candidate}{" "}
        <span className={`ship ${r.ship ? "ship--yes" : "ship--no"}`}>
          {r.ship ? "✓ Ship" : "✗ Do not ship"}
        </span>
      </h2>
      <p className="lede">
        Against production {r.production} on the {r.split} split.{" "}
        {r.failed.length
          ? `Failed: ${r.failed.map((f) => f.split(": ")[1]).join(", ")}.`
          : "Every gate passed."}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th scope="col">Gate</th>
              <th scope="col">Metric</th>
              <th scope="col" className="num">
                Result
              </th>
              <th scope="col" className="num">
                Limit
              </th>
              <th scope="col" className="num">
                95% interval
              </th>
              <th scope="col">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {r.checks.map((c) => {
              const floor = c.rule === "floor";
              return (
                <tr key={`${c.rule}-${c.metric}`}>
                  <td>{floor ? "Floor" : "Not worse than production"}</td>
                  <th scope="row">{metricName(c.metric)}</th>
                  <td className="num">{floor ? pct(c.value) : signedPts(c.value)}</td>
                  <td className="num">{floor ? pct(c.limit, 0) : signedPts(c.limit)}</td>
                  <td className="num">
                    {c.low === null ? "" : `${signedPts(c.low)} to ${signedPts(c.high)}`}
                  </td>
                  <td>
                    <span
                      className={
                        c.status === "fail"
                          ? "verdict verdict--bad"
                          : c.status === "pass"
                            ? "verdict verdict--good"
                            : "verdict verdict--other"
                      }
                    >
                      {c.status === "fail" ? "✗ fails" : c.status === "pass" ? "✓ passes" : "no cases"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="lede" style={{ marginTop: "var(--space-sm)" }}>
        Evidence kept in the trace archive: {r.evidence_runs.join(", ")}
      </p>
    </section>
  );
}

export function ReleasesScreen() {
  const q = useQuery({ queryKey: ["releases"], queryFn: api.releases });
  return (
    <>
      <h1>Releases</h1>
      <p className="lede">
        A candidate agent ships only if it meets every floor and is not worse than production, with 95%
        confidence, on packages nobody tuned on.
      </p>
      <Async
        q={q}
        what="release decisions"
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No release has been decided yet.">
            <p>
              Run <code>aae release baseline-strict</code> to compare a candidate with production.
            </p>
          </EmptyState>
        }
      >
        {(rows) => rows.map((r) => <Decision key={r.candidate} r={r} />)}
      </Async>
    </>
  );
}
