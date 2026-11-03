import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../shared/api/client";
import type { JudgeReport } from "../../shared/api/types";
import { Async, EmptyState } from "../../shared/ui/States";
import { pct, usd } from "../../shared/ui/format";

function Judge({ d }: { d: JudgeReport }) {
  const o = d.overall;
  return (
    <>
      <p className="lede">
        {d.items} findings judged by {d.model} for {usd(d.cost_usd)}. On findings whose truth is known, the
        judge accepts {pct(o.sensitivity)} of the right ones and rejects {pct(o.specificity)} of the wrong
        ones (κ {o.kappa?.toFixed(2) ?? "–"}).
      </p>
      <section className="panel" aria-labelledby="conf-h">
        <h2 id="conf-h" style={{ marginTop: 0 }}>
          Judge against the seeded truth
        </h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Truth</th>
              <th scope="col" className="num">
                Judge accepts
              </th>
              <th scope="col" className="num">
                Judge rejects
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Right finding</th>
              <td className="num">{o.tp}</td>
              <td className="num">{o.fn}</td>
            </tr>
            <tr>
              <th scope="row">Wrong finding</th>
              <td className="num">{o.fp}</td>
              <td className="num">{o.tn}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <h2>Precision without truth</h2>
      <p>
        Calibrated on half of the packages, the judge estimates each agent's precision on the other half. The
        raw share it accepts is biased by its own errors; the corrected estimate removes that bias.
      </p>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th scope="col">Agent</th>
              <th scope="col" className="num">
                Findings
              </th>
              <th scope="col" className="num">
                Judge accepts
              </th>
              <th scope="col" className="num">
                Corrected estimate
              </th>
              <th scope="col" className="num">
                Truth
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(d.holdout.agents).map(([agent, a]) => (
              <tr key={agent}>
                <th scope="row">{agent}</th>
                <td className="num">{a.findings}</td>
                <td className="num">{pct(a.naive_precision)}</td>
                <td className="num">
                  {pct(a.corrected_precision)}{" "}
                  <span className="lede">
                    ({pct(a.low, 0)} – {pct(a.high, 0)})
                  </span>
                </td>
                <td className="num">{pct(a.truth_precision)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function JudgeScreen() {
  const q = useQuery({
    queryKey: ["judge", "llm"],
    queryFn: async (): Promise<JudgeReport | null> => {
      try {
        return await api.judge("llm");
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null; // not calibrated yet: an empty state
        throw e;
      }
    },
  });
  return (
    <>
      <h1>Judge</h1>
      <p className="lede">
        A model that checks findings where no ground truth exists, and how far to trust it.
      </p>
      <Async
        q={q}
        what="the judge's calibration"
        isEmpty={(d) => d === null || d.items === 0}
        empty={
          <EmptyState title="The judge has not been calibrated.">
            <p>
              Run <code>aae judge calibrate</code>; it judges a fixed sample of findings whose truth is known.
            </p>
          </EmptyState>
        }
      >
        {(d) => d && <Judge d={d} />}
      </Async>
    </>
  );
}
