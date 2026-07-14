import { expect, test } from "@playwright/test";

test("public landing surface exposes its decision-support boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Trade with discipline/i })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Username" })).toBeVisible();
  await expect(page.getByText(/Decision support, not a profit promise/i)).toBeVisible();
});

test("plans remain public and disclose the billing boundary", async ({ page }) => {
  await page.route("**/api/subscriptions/plans", async (route) => route.fulfill({ json: { plans: [{ code: "free", name: "Free", description: "Decision support", price_monthly_inr: 0, entitlements: [], limits: {} }] } }));
  await page.goto("/plans");
  await expect(page.getByRole("heading", { name: "Choose the access you need." })).toBeVisible();
  await expect(page.getByText(/Billing is not connected yet/i)).toBeVisible();
});

test("signup validates confirmation before sending registration", async ({ page }) => {
  let registrations = 0;
  await page.route("**/api/auth/register", async (route) => { registrations += 1; await route.abort(); });
  await page.goto("/signup");
  const signup = page.getByRole("article");
  await signup.getByLabel("Username").fill("new-user");
  await signup.getByLabel("Password", { exact: true }).fill("StrongPass1!");
  await signup.getByLabel("Confirm password").fill("DifferentPass1!");
  await signup.getByRole("button", { name: "Create free account" }).click();
  await expect(signup.getByRole("alert")).toHaveText("Passwords do not match.");
  expect(registrations).toBe(0);
});
