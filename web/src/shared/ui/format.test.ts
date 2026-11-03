import { metricName, pct, scale, signedPts, usd } from "./format";

test("percentages and missing values", () => {
  expect(pct(0.9623)).toBe("96.2 %");
  expect(pct(null)).toBe("–");
});

test("signed differences read as points", () => {
  expect(signedPts(-0.049)).toBe("−4.9 pts");
  expect(signedPts(0.01)).toBe("+1.0 pts");
  expect(signedPts(0)).toBe("±0.0 pts");
});

test("scale clamps to the axis", () => {
  expect(scale(0.5, 400)).toBe(200);
  expect(scale(1.2, 400)).toBe(400);
  expect(scale(-0.1, 400)).toBe(0);
});

test("costs keep small amounts visible", () => {
  expect(usd(0.0093)).toBe("$0.0093");
  expect(usd(2.636)).toBe("$2.64");
});

test("metric names", () => {
  expect(metricName("recall:prior_year")).toBe("Recall: prior year");
  expect(metricName("clean_false_alarm_rate")).toBe("Clean packages with a wrong flag");
});
