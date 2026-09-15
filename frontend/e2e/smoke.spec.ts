import { expect, test } from "@playwright/test";

test("renders a useful offline state when the local core is not running", async ({ page }) => {
  // Keep this scenario deterministic even when a developer has an installed
  // DS5Forge core listening on the host. Offline UX must not depend on the
  // machine running the Playwright suite.
  await page.route("http://127.0.0.1:8765/**", (route) => route.abort());
  await page.routeWebSocket("ws://127.0.0.1:8765/**", (socket) => {
    socket.close({ code: 1011, reason: "offline smoke" });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("status").getByText("Local core offline", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("status").getByText(/DS5Forge will retry automatically; use Settings > Restart Core/),
  ).toBeVisible();
  await expect(page.getByRole("complementary").getByText("DS5Forge", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("status").getByText("Core unavailable", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /check for updates/i })).toBeEnabled();
  await expect(page.getByRole("button", { name: /restart core/i })).toBeEnabled();
});
