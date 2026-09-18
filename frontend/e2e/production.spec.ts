import { test, expect, type Page } from "@playwright/test";

const APP_ROUTES = [
  "/",
  "/app",
  "/app/projects",
  "/app/projects/new",
  "/app/projects/0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21",
  "/app/projects/0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21/policy",
  "/app/projects/0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21/releases",
  "/app/projects/0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21/security",
  "/app/releases/new",
  "/app/releases/1",
  "/app/releases/1/review",
  "/app/releases/1/evidence",
  "/app/releases/1/consensus",
  "/app/releases/1/transactions",
  "/app/activity",
  "/app/settings",
];

async function auditRoute(page: Page, route: string): Promise<void> {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const badResponses: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || /hydration|useSyncExternalStore|maximum update depth/i.test(message.text())) consoleErrors.push(`${message.text()} @ ${message.location().url}`);
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || "failed"}`));
  page.on("response", (response) => { if (response.status() >= 400) badResponses.push(`${response.status()} ${response.url()}`); });
  if ((process.env.SENTINELX_BROWSER_BASE_URL || "").includes("localhost")) {
    await page.route("https://studio.genlayer.com/api", async (requestRoute) => {
      const payload = requestRoute.request().postDataJSON() as { method?: string } | null;
      await requestRoute.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ jsonrpc: "2.0", id: 1, result: payload?.method === "eth_chainId" ? "0xf22f" : "0x100" }) });
    });
  }
  await page.goto(route, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("0x178Cc14e39E5873C4EaB2590B1a94b92694545ac");
  expect(bodyText).not.toContain("0x9e0e22C8f35312E75C66f0255d4559f90e4fCd09");
  expect(bodyText).not.toContain("studio-dev");
  expect(bodyText).not.toContain("61997");
  if (consoleErrors.length || pageErrors.length || failedRequests.length || badResponses.length) console.log(JSON.stringify({ route, consoleErrors, pageErrors, failedRequests, badResponses }, null, 2));
  await expect(page.locator("body")).not.toContainText("Something went wrong");
  await expect(page.locator("body")).toContainText("Studionet");
  await expect(page.locator("body")).toContainText("61999");
  expect(consoleErrors, `${route} console errors`).toEqual([]);
  expect(pageErrors, `${route} page errors`).toEqual([]);
  expect(failedRequests.filter((entry) => !entry.includes("favicon")), `${route} failed requests`).toEqual([]);
}

test.describe("SentinelX production browser routes", () => {
  for (const route of APP_ROUTES) {
    test(route, async ({ page }) => auditRoute(page, route));
  }

  test("survives corrupt transaction storage", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("sentinelx.transaction-center.v1", "not-json"));
    await auditRoute(page, "/app");
  });

  test("survives valid transaction storage with duplicate operation names", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("sentinelx.transaction-center.v1", JSON.stringify([
      { operation: "review", hash: `0x${"a".repeat(64)}`, submittedAt: new Date(0).toISOString(), lifecycle: { state: "processing" }, childTransactionIds: [], verification: "pending" },
      { operation: "review", hash: `0x${"b".repeat(64)}`, submittedAt: new Date(0).toISOString(), lifecycle: { state: "finalized" }, childTransactionIds: [], verification: "successful" },
    ])));
    await auditRoute(page, "/app/activity");
    await expect(page.locator("body")).toContainText("review");
  });

  test("renders canonical verified release data in production", async ({ page }) => {
    test.skip((process.env.SENTINELX_BROWSER_BASE_URL || "").includes("localhost"), "canonical chain assertion is production-only");
    await page.goto("/app/releases/1", { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText("VERIFIED", { timeout: 10_000 });
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).toContain("1073b34f14");
    expect(bodyText).toContain("0xaF9ABA4D");
    expect(bodyText).not.toContain("Something went wrong");
  });
});
