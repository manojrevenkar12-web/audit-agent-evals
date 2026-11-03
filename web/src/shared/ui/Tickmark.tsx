// Auditors mark working papers with tick marks; the console uses the same marks for the evaluator's verdicts.
const MARKS: Record<string, { glyph: string; tone: "good" | "bad" | "other"; text: string }> = {
  hit: { glyph: "✓", tone: "good", text: "Found a seeded error" },
  duplicate: { glyph: "✓✓", tone: "good", text: "Found it again" },
  mistyped: { glyph: "≠", tone: "bad", text: "Right place, wrong kind of error" },
  decoy: { glyph: "Ⓡ", tone: "bad", text: "Flagged a disclosed restatement" },
  rounding: { glyph: "≈", tone: "bad", text: "Flagged a rounding difference" },
  unlocated: { glyph: "?", tone: "other", text: "Points at nothing on the page" },
  false_alarm: { glyph: "✗", tone: "bad", text: "Not an error" },
};

export function Tickmark({ verdict, withText = true }: { verdict: string; withText?: boolean }) {
  const m = MARKS[verdict] ?? { glyph: "·", tone: "other" as const, text: verdict };
  return (
    <span className={`verdict verdict--${m.tone}`} title={m.text}>
      <span aria-hidden="true">{m.glyph}</span>
      <span className={withText ? undefined : "visually-hidden"}>{m.text}</span>
    </span>
  );
}

export const VERDICT_ORDER = Object.keys(MARKS);
