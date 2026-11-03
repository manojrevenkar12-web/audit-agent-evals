import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type FormEvent, useEffect, useState } from "react";
import { api } from "../../shared/api/client";
import type { Label, QueueItem } from "../../shared/api/types";
import { layout, motionTiming } from "../../shared/theme/tokens";
import { Async, EmptyState } from "../../shared/ui/States";
import { Tickmark } from "../../shared/ui/Tickmark";

const LABELS: { value: Label; text: string; hint: string }[] = [
  { value: "valid", text: "A real error", hint: "It must be corrected before sign-off." },
  { value: "invalid", text: "Not an error", hint: "The figures or text are right." },
  {
    value: "out_of_scope",
    text: "A fair point, but not an error",
    hint: "Worth raising; not what this review covers.",
  },
];

const REVIEWER_KEY = "aae.reviewer";

function readReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

function Detail({ item, onDone }: { item: QueueItem; onDone: () => void }) {
  const f = item.finding;
  const qc = useQueryClient();
  const [reviewer, setReviewer] = useState(readReviewer);
  const [label, setLabel] = useState<Label | "">("");
  const [note, setNote] = useState("");
  const [page, setPage] = useState(f.page ?? 1);
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => {
    setLabel("");
    setNote("");
    setPage(f.page ?? 1);
    setImageFailed(false);
  }, [f.page]);
  const save = useMutation({
    mutationFn: () => api.label(item.id, { reviewer, label: label as Label, note }),
    onSuccess: () => {
      try {
        localStorage.setItem(REVIEWER_KEY, reviewer);
      } catch {
        /* the name is a convenience only */
      }
      qc.invalidateQueries({ queryKey: ["queue"] });
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (reviewer.trim() && label) save.mutate();
  };
  return (
    <div className="review">
      <figure style={{ margin: 0, maxWidth: layout.reviewImage }}>
        {imageFailed ? (
          <div className="state state--error" role="alert">
            <p>The page image could not be loaded. The package may not be built on this machine.</p>
            <button type="button" onClick={() => setImageFailed(false)}>
              Try again
            </button>
          </div>
        ) : (
          <img
            className="page-image"
            src={api.pageUrl(item.split, item.package, f.document, page)}
            alt={`Page ${page} of ${f.document} in ${item.package}`}
            onError={() => setImageFailed(true)}
          />
        )}
        <figcaption className="lede">
          {item.package} · {f.document} · page {page}{" "}
          <button
            type="button"
            className="btn btn--quiet"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            Previous page
          </button>{" "}
          <button type="button" className="btn btn--quiet" onClick={() => setPage((p) => p + 1)}>
            Next page
          </button>
        </figcaption>
      </figure>
      <section className="panel" aria-labelledby="finding-h">
        <h2 id="finding-h" style={{ marginTop: 0 }}>
          {f.type.replace("_", " ")} raised by {item.agent}
        </h2>
        <p>{f.explanation}</p>
        <dl className="facts">
          {f.row_label && (
            <>
              <dt>Line item</dt>
              <dd>{f.row_label}</dd>
            </>
          )}
          {f.column && (
            <>
              <dt>Column</dt>
              <dd>{f.column}</dd>
            </>
          )}
          {f.quote && (
            <>
              <dt>Quote</dt>
              <dd>{f.quote}</dd>
            </>
          )}
          {(f.found_value || f.expected_value) && (
            <>
              <dt>Shown / expected</dt>
              <dd>
                {f.found_value ?? "–"} / {f.expected_value ?? "–"}
              </dd>
            </>
          )}
          <dt>Evaluator</dt>
          <dd>
            <Tickmark verdict={item.verdict} />
          </dd>
          <dt>Judge</dt>
          <dd>
            {item.judge_valid === null ? "no answer" : item.judge_valid ? "a real error" : "not an error"}
            {item.judge_reason && <span className="lede"> — {item.judge_reason}</span>}
          </dd>
          <dt>Why it is here</dt>
          <dd>{item.reason}</dd>
        </dl>
        <form onSubmit={submit}>
          <fieldset>
            <legend>Your decision</legend>
            {LABELS.map((l) => (
              <label key={l.value} style={{ marginBottom: "var(--space-xs)" }}>
                <input
                  type="radio"
                  name="label"
                  value={l.value}
                  checked={label === l.value}
                  onChange={() => setLabel(l.value)}
                />{" "}
                <strong>{l.text}</strong> <span className="lede">{l.hint}</span>
              </label>
            ))}
          </fieldset>
          <label htmlFor="note">Note (optional)</label>
          <textarea id="note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          <label htmlFor="reviewer" style={{ marginTop: "var(--space-sm)" }}>
            Your name
          </label>
          <input
            id="reviewer"
            type="text"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            autoComplete="name"
          />
          {save.isError && (
            <p role="alert" className="verdict--bad">
              The decision was not saved: {(save.error as Error).message}
            </p>
          )}
          <p style={{ marginTop: "var(--space-md)" }}>
            <button type="submit" className="btn" disabled={!reviewer.trim() || !label || save.isPending}>
              {save.isPending ? "Saving decision…" : "Save decision"}
            </button>
          </p>
        </form>
      </section>
    </div>
  );
}

function Queue({ items }: { items: QueueItem[] }) {
  const [selected, setSelected] = useState(items[0]?.id);
  const [saved, setSaved] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const current = items.find((i) => i.id === selected) ?? items[0];
  const next = () => {
    const at = items.findIndex((i) => i.id === current.id);
    setSaved(`Decision saved for ${current.package} #${current.idx}.`);
    setSelected(items[at + 1]?.id ?? items[0]?.id);
  };
  return (
    <>
      <output className="status" aria-live="polite">
        {saved}
      </output>
      <nav aria-label="Findings to review" className="review__list">
        {items.slice(0, 12).map((i) => (
          <button
            key={i.id}
            type="button"
            className="review__item"
            aria-current={i.id === current.id}
            onClick={() => setSelected(i.id)}
          >
            <strong>
              {i.package} #{i.idx}
            </strong>{" "}
            {i.type.replace("_", " ")} by {i.agent} — <span className="lede">{i.reason}</span>
          </button>
        ))}
      </nav>
      {items.length > 12 && <p className="lede">and {items.length - 12} more, most useful first.</p>}
      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? undefined : { opacity: 0 }}
          transition={motionTiming.enter}
        >
          <Detail item={current} onDone={next} />
        </motion.div>
      </AnimatePresence>
    </>
  );
}

export function ReviewScreen() {
  const q = useQuery({ queryKey: ["queue", "open"], queryFn: () => api.queue("open") });
  return (
    <>
      <h1>Review queue</h1>
      <p className="lede">
        Findings the seeded truth cannot settle, or where the judge disagrees with it. Your decisions become
        part of the golden set.
      </p>
      <Async
        q={q}
        what="the review queue"
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="Nothing is waiting for review.">
            <p>
              New items arrive after <code>aae judge calibrate</code> and <code>aae queue build</code>.
            </p>
          </EmptyState>
        }
      >
        {(items) => <Queue items={items} />}
      </Async>
    </>
  );
}
