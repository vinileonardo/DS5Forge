import { expect, test } from "@playwright/test";

test("renders a useful offline state when the local core is not running", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("main").getByText("Local core offline", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary").getByText("DS5Forge", { exact: true })).toBeVisible();
});
