import { test, expect } from "@playwright/test";

test("Glyph lighting controls follow per-effect capabilities", async ({
  page,
}) => {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Lighting", exact: true }),
  ).toBeVisible();

  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Disconnect", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply lighting", exact: true }),
  ).toBeEnabled();

  const effect = page.getByLabel("Effect", { exact: true });
  await effect.selectOption("off");
  await expect(page.getByLabel("Color", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel(/Brightness/)).toHaveCount(0);
  await expect(page.getByLabel(/Speed/)).toHaveCount(0);
  await expect(page.getByLabel("Rainbow", { exact: true })).toHaveCount(0);

  await effect.selectOption("wave");
  await expect(page.getByLabel("Color", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/Brightness/)).toHaveAttribute("max", "4");
  await expect(page.getByLabel(/Speed/)).toHaveAttribute("max", "4");
  await expect(page.getByLabel("Effect option", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Rainbow", { exact: true })).toBeVisible();

  await page.getByLabel("Effect option", { exact: true }).selectOption("3");
  await page
    .getByRole("button", { name: "Apply lighting", exact: true })
    .click();
  await expect(
    page.getByText("Lighting read back from keyboard."),
  ).toBeVisible();

  await effect.selectOption("solid");
  await expect(page.getByLabel("Effect option", { exact: true })).toHaveCount(
    0,
  );
  await page
    .getByRole("button", { name: "Side lighting", exact: true })
    .click();
  await effect.selectOption("wave");
  await expect(page.getByLabel(/Speed/)).toHaveAttribute("max", "3");
  await expect(page.getByLabel("Effect option", { exact: true })).toHaveCount(
    0,
  );

  await page
    .getByRole("button", { name: "Main lighting", exact: true })
    .click();
  await effect.selectOption("picture");
  await expect(page.getByLabel("Effect option", { exact: true })).toBeVisible();
  await expect(
    page.getByLabel("Effect option", { exact: true }).locator("option"),
  ).toHaveText([
    "Pattern 1",
    "Pattern 2",
    "Pattern 3",
    "Pattern 4",
    "Pattern 5",
  ]);
  await expect(page.getByLabel("Color", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel(/Speed/)).toHaveCount(0);
  await expect(page.getByLabel("Rainbow", { exact: true })).toHaveCount(0);

  await effect.selectOption("neon");
  await expect(page.getByLabel("Color", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Rainbow", { exact: true })).toHaveCount(0);

  await effect.selectOption("music");
  await expect(
    page.getByText("Music-follow input is not provided by this host yet."),
  ).toBeVisible();
});
