// End-to-end check of the main workflow against a running stack.
// Usage: BASE_URL=http://127.0.0.1:3000 node e2e/workflow.mjs [screenshot-dir]
// Needs: API (JOBS_MODE=thread) and web running, Playwright with Chromium installed.
import { createRequire } from "node:module";

// CommonJS resolution so a globally installed Playwright (NODE_PATH) works as well as a local one.
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const SHOTS = process.argv[2] ?? null;
const email = `e2e-${Date.now()}@example.com`;
const password = "correct-horse-battery";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const problems = [];
page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
page.on("response", (r) => {
  if (r.url().includes("/api/v1/") && r.status() >= 500) problems.push(`HTTP ${r.status()} ${r.url()}`);
});

let n = 0;
async function step(name, fn) {
  const t = Date.now();
  await fn();
  n += 1;
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${String(n).padStart(2, "0")}-${name}.png`, fullPage: true });
  console.log(`ok  ${name} (${Date.now() - t} ms)`);
}

try {
  await step("register", async () => {
    await page.goto(`${BASE}/login`);
    await page.getByRole("button", { name: "No account yet? Create one" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await page.getByRole("heading", { name: "Overview" }).waitFor();
  });

  await step("demo-data", async () => {
    await page.goto(`${BASE}/settings`);
    await page.getByRole("button", { name: "Generate demo data" }).click();
    await page.getByText("Created synthetic BTCUSDT 1h data").waitFor();
  });

  let strategyUrl = "";
  await step("create-strategy", async () => {
    await page.goto(`${BASE}/strategies/new`);
    await page.getByRole("radio", { name: /EMA crossover/ }).click();
    await page.getByRole("button", { name: "Save strategy" }).click();
    await page.waitForURL(/\/strategies\/[0-9a-f-]{36}/);
    strategyUrl = page.url().split("?")[0];
    await page.getByRole("button", { name: "Run backtest" }).waitFor();
  });

  let backtestUrl = "";
  await step("backtest-result", async () => {
    await page.getByRole("button", { name: "Run backtest" }).click();
    await page.waitForURL(/\/backtests\/[0-9a-f-]{36}/);
    backtestUrl = page.url();
    await page.getByText(/^Trades \(\d+\)$/).waitFor({ timeout: 60_000 });
    await page.getByText("Reproducibility").waitFor();
    await page.getByText("Synthetic data").first().waitFor();
  });

  await step("trade-list", async () => {
    const rows = page.locator("section", { hasText: /^Trades \(/ }).locator("tbody tr");
    const count = await rows.count();
    if (count === 0) throw new Error("trade table is empty");
    console.log(`    ${count} trade rows on the first page`);
  });

  await step("save-version", async () => {
    await page.goto(`${strategyUrl}?tab=logic`);
    await page.getByRole("tab", { name: "Logic" }).click();
    await page.getByLabel("Indicator 1 period").fill("15");
    await page.getByRole("button", { name: "Save as new version" }).click();
    await page.getByText("Saved as v2.").waitFor();
  });

  await step("validation", async () => {
    await page.getByRole("tab", { name: "Validation" }).click();
    await page.getByRole("button", { name: "Run validation" }).click();
    await page.getByText("Chronological splits").waitFor({ timeout: 90_000 });
  });

  await step("paper-session", async () => {
    await page.goto(backtestUrl);
    await page.getByRole("link", { name: "Start paper session" }).click();
    await page.waitForURL(/\/paper\?/);
    await page.getByRole("button", { name: "Create session" }).click();
    await page.waitForURL(/\/paper\/[0-9a-f-]{36}/);
    await page.getByRole("button", { name: "Start", exact: true }).click();
    await page.getByRole("button", { name: "Advance" }).click();
    await page.getByText(/Processed \d+ candles/).waitFor();
  });

  await step("journal", async () => {
    await page.goto(`${BASE}/journal`);
    await page.getByRole("button", { name: "Add trade" }).first().click();
    const form = page.locator("form", { has: page.getByLabel("Entry price") });
    await form.getByLabel("Entry time (UTC)").fill("2024-03-01T10:00");
    await form.getByLabel("Entry price").fill("60000");
    await form.getByLabel("Quantity").fill("0.1");
    await form.getByLabel("Exit price (optional)").fill("61000");
    await form.getByRole("button", { name: "Add trade" }).click();
    await page.locator("tbody tr", { hasText: "BTCUSDT" }).first().waitFor();
  });

  await step("discovery", async () => {
    await page.goto(`${BASE}/discover`);
    await page.getByRole("button", { name: "Start discovery" }).click();
    await page.waitForURL(/\/discover\/[0-9a-f-]{36}/);
    await page.getByRole("heading", { name: "Candidates" }).waitFor({ timeout: 180_000 });
  });

  await step("overview", async () => {
    await page.goto(`${BASE}/`);
    await page.getByText("Recent backtests").waitFor();
  });

  if (problems.length) throw new Error(problems.join("\n"));
  console.log("E2E workflow passed");
} catch (e) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/failure.png`, fullPage: true }).catch(() => {});
  console.error("E2E workflow failed:", e.message);
  if (problems.length) console.error(problems.join("\n"));
  process.exitCode = 1;
} finally {
  await browser.close();
}
