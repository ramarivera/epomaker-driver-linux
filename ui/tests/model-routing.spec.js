import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/#token=ui-test-token");
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
});

async function connect(page, label) {
  await page.getByLabel("Device", { exact: true }).selectOption({ label });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Keyboard connected.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Keymap", exact: true }),
  ).toBeVisible();
}

test("HE descriptor drives profile, Fn and submode controls", async ({
  page,
}) => {
  await connect(page, "HE65 Mag simulator · usb");
  await expect(
    page.getByLabel("Profile", { exact: true }).locator("option"),
  ).toHaveCount(4);
  await expect(page.getByLabel("Submode", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Fn Windows", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Fn Mac", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(page.getByLabel("Macro slot", { exact: true })).toHaveAttribute(
    "max",
    "255",
  );
});

test("reconnecting Glyph resets model-specific keymap controls", async ({
  page,
}) => {
  await connect(page, "HE65 Mag simulator · usb");
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Keyboard connected.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Profile", { exact: true }).locator("option"),
  ).toHaveCount(3);
  await expect(page.getByLabel("Submode", { exact: true })).toHaveCount(0);
});

test("wired HE and legacy descriptors hide unsupported controls", async ({
  page,
}) => {
  await connect(page, "HE60 Lite simulator · usb");
  await expect(
    page.getByRole("button", { name: "Display", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Side lighting", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sleep timers", exact: true }),
  ).toHaveCount(0);

  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "RT100 legacy simulator · usb" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Keyboard connected.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Fn", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Fn Mac", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toHaveCount(0);
});

test("HE65 Mag display uses model dimensions and omits system information", async ({
  page,
}) => {
  await connect(page, "HE65 Mag simulator · usb");
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await expect(page.getByText(/128 × 128 pixels/)).toBeVisible();
  await expect(
    page.getByText(/Animations support up to 165 frames/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send system information", exact: true }),
  ).toHaveCount(0);
});

test("HE65 V2 exposes only its public sleep fields", async ({ page }) => {
  await connect(page, "HE65 V2 simulator · usb");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sleep timers", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel(/Bluetooth sleep/)).toBeVisible();
  await expect(page.getByLabel(/Receiver sleep/)).toBeVisible();
  await expect(page.getByLabel(/deep Bluetooth/)).toBeVisible();
  await expect(page.getByLabel(/deep Receiver/)).toHaveCount(0);
});
