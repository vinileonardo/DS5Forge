import { expect, test } from "@playwright/test";

test("renders a useful offline state when the local core is not running", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("status").getByText("Local core offline", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("status").getByText(/DS5Forge will retry automatically; use Settings > Restart Core/),
  ).toBeVisible();
  await expect(page.getByRole("complementary").getByText("DS5Forge", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("Core preferences unavailable")).toBeVisible();
  await expect(page.getByRole("button", { name: /check for updates/i })).toBeEnabled();
  await expect(page.getByRole("button", { name: /restart core/i })).toBeEnabled();
});
