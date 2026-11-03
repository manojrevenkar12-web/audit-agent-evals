import AxeBuilder from "@axe-core/playwright";
import { type Page, type Route, expect, test } from "@playwright/test";
import evals from "./fixtures/evals.json" with { type: "json" };
import judge from "./fixtures/judge.json" with { type: "json" };
import queue from "./fixtures/queue.json" with { type: "json" };
import releases from "./fixtures/releases.json" with { type: "json" };

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function mockApi(page: Page, overrides: Record<string, (route: Route) => Promise<void>> = {}) {
  const labels: unknown[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    for (const [prefix, handler] of Object.entries(overrides)) {
      if (url.pathname.startsWith(prefix)) return handler(route);
    }
    if (url.pathname === "/api/evals") return route.fulfill({ json: evals });
    if (url.pathname === "/api/releases") return route.fulfill({ json: releases });
    if (url.pathname.startsWith("/api/judge/")) return route.fulfill({ json: judge });
    if (url.pathname === "/api/queue") return route.fulfill({ json: queue });
    if (url.pathname.endsWith("/labels") && route.request().method() === "POST") {
      labels.push(route.request().postDataJSON());
      return route.fulfill({ status: 201, json: { ok: true } });
    }
    if (url.pathname.includes("/pages/")) return route.fulfill({ body: PNG, contentType: "image/png" });
    return route.fulfill({ status: 404, json: { detail: "not found" } });
  });
  return labels;
}

async function expectAccessible(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(result.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
}

test("results compare agents with intervals, by kind and by verdict", async ({ page }) => {
  await mockApi(page);
  await page.goto("/#/results");
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  await page.getByRole("button", { name: "llm split" }).click();
  await expect(page.getByRole("img", { name: /Recall by agent with 95% intervals/ })).toBeVisible();
  await page.getByRole("button", { name: "Recall, scanned documents" }).click();
  await expect(page.getByRole("heading", { name: "Recall, scanned documents" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "claude-sonnet@1" }).first()).toBeVisible();
  await expect(page.getByText("Flagged a rounding difference")).toBeVisible();
  await expectAccessible(page);
});

test("release decisions show every gate and the evidence", async ({ page }) => {
  await mockApi(page);
  await page.goto("/#/releases");
  await expect(page.getByRole("heading", { name: /baseline-strict/ })).toContainText("Do not ship");
  await expect(page.getByRole("heading", { name: /hybrid-haiku/ })).toBeVisible();
  await expect(page.getByText(/Evidence kept in the trace archive/).first()).toBeVisible();
  await expectAccessible(page);
});

test("the judge's calibration and corrected precision", async ({ page }) => {
  await mockApi(page);
  await page.goto("/#/judge");
  await expect(page.getByRole("heading", { name: "Judge against the seeded truth" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Precision without truth" })).toBeVisible();
  await expectAccessible(page);
});

test("a reviewer labels a finding and moves to the next", async ({ page }) => {
  const labels = await mockApi(page);
  await page.goto("/#/review");
  await expect(page.getByRole("navigation", { name: "Findings to review" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Page \d+ of/ })).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel(/Not an error/).check();
  await page.getByLabel("Your name").fill("Ana Weber");
  await page.getByLabel("Note (optional)").fill("Comparative agrees with last year's report.");
  await page.getByRole("button", { name: "Save decision" }).click();
  await expect(page.getByText(/Decision saved for/)).toBeVisible();
  expect(labels).toEqual([
    { reviewer: "Ana Weber", label: "invalid", note: "Comparative agrees with last year's report." },
  ]);
});

test("a failed load explains itself and retries", async ({ page }) => {
  let calls = 0;
  await mockApi(page, {
    "/api/evals": async (route) => {
      calls += 1;
      if (calls <= 2) return route.fulfill({ status: 500, json: { detail: "ClickHouse is restarting" } });
      return route.fulfill({ json: evals });
    },
  });
  await page.goto("/#/results");
  await expect(page.getByRole("alert")).toContainText("Could not load results.");
  await expect(page.getByRole("alert")).toContainText("ClickHouse is restarting");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("img", { name: /by agent with 95% intervals/ })).toBeVisible();
});

test("empty states say what to run", async ({ page }) => {
  await mockApi(page, {
    "/api/evals": (route) => route.fulfill({ json: [] }),
    "/api/queue": (route) => route.fulfill({ json: [] }),
    "/api/judge": (route) =>
      route.fulfill({ status: 404, json: { detail: "llm.json has not been produced yet" } }),
  });
  await page.goto("/#/results");
  await expect(page.getByText("No evaluation has been run yet.")).toBeVisible();
  await page.goto("/#/review");
  await expect(page.getByText("Nothing is waiting for review.")).toBeVisible();
  await page.goto("/#/judge");
  await expect(page.getByText("The judge has not been calibrated.")).toBeVisible();
});

test("a skeleton shows while results load", async ({ page }) => {
  await mockApi(page, {
    "/api/evals": async (route) => {
      await new Promise((r) => setTimeout(r, 800));
      await route.fulfill({ json: evals });
    },
  });
  await page.goto("/#/results");
  await expect(page.getByLabel("Loading results")).toBeVisible();
  await expect(page.getByRole("img", { name: /by agent with 95% intervals/ })).toBeVisible();
});

test("works on a phone without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  for (const screen of ["results", "releases", "judge", "review"]) {
    await page.goto(`/#/${screen}`);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, screen).toBeLessThanOrEqual(0);
  }
});
