# 3. A calibrated judge for traffic without truth; people for what neither settles

**Context.** In production there is no seeded truth, and agents raise points the truth does not cover
(a missing secured-liabilities note, an appropriation proposal that ignores the profit carried forward).

**Decision.** A model judges each finding from the PDFs. Its sensitivity and specificity are measured on seeded
findings, including hard negatives (rounding differences, the restatement). Precision on unlabelled traffic is
the judge's acceptance rate corrected for those rates (Rogan–Gladen), with an interval that resamples both the
calibration and the traffic. Findings the truth cannot settle, and those where judge and truth disagree, go to
a review queue; people's settled labels join the golden set.

**Consequences.** The judge's disagreements with the truth are a second check on the truth itself: they surfaced
that the matcher credits a finding at a symptom (a correct sentence next to a wrong comparative) as finding the
cause. That is documented rather than silently re-scored.
