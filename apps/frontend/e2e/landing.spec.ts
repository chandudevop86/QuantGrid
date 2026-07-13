import { expect, test } from "@playwright/test";

test("public landing surface exposes its decision-support boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Trade with discipline/i })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Username" })).toBeVisible();
  await expect(page.getByText(/Decision support, not a profit promise/i)).toBeVisible();
});
