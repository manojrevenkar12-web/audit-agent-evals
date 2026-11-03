export type Metric = { value: number | null; low: number | null; high: number | null; n: number; k: number };

export type EvalSummary = {
  agent: string;
  name: string;
  split: string;
  packages: number;
  defects: number;
  findings: number;
  verdicts: Record<string, number>;
  metrics: Record<string, Metric>;
  operational: Record<string, number>;
  run_id?: string | null;
};

export type Check = {
  rule: string;
  metric: string;
  status: "pass" | "fail" | "n/a";
  value: number | null;
  limit: number;
  low: number | null;
  high: number | null;
  detail: string;
};

export type Release = {
  candidate: string;
  production: string;
  split: string;
  decided_at: string;
  ship: boolean;
  failed: string[];
  checks: Check[];
  watch: Record<string, number | null>;
  evidence_runs: string[];
};

export type Rates = {
  n: number;
  tp: number;
  fn: number;
  tn: number;
  fp: number;
  sensitivity: number | null;
  specificity: number | null;
  agreement: number | null;
  kappa: number | null;
};

export type JudgeReport = {
  split: string;
  model: string;
  items: number;
  errors: number;
  cost_usd: number;
  overall: Rates;
  by_agent: Record<string, Rates>;
  holdout: {
    calibration: Rates;
    agents: Record<
      string,
      {
        findings: number;
        naive_precision: number;
        corrected_precision: number | null;
        low: number | null;
        high: number | null;
        truth_precision: number | null;
      }
    >;
  };
};

export type Finding = {
  type: string;
  document: string;
  page?: number | null;
  row_label?: string | null;
  column?: string | null;
  quote?: string | null;
  found_value?: string | null;
  expected_value?: string | null;
  explanation: string;
  confidence?: number;
};

export type QueueItem = {
  id: string;
  split: string;
  agent: string;
  package: string;
  idx: number;
  type: string;
  finding: Finding;
  verdict: string;
  truth_label: string;
  judge_valid: boolean | null;
  judge_reason: string;
  judge_confidence: number;
  reason: string;
  priority: number;
  reviews_needed: number;
  labels: Record<string, string>;
  status: "open" | "done";
};

export type Label = "valid" | "invalid" | "out_of_scope";
