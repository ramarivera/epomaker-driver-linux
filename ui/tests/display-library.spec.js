import { test, expect } from "@playwright/test";

const onePixelPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function openDisplay(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Display asset library", exact: true }),
  ).toBeVisible();
}

test("display assets save, reload, load, and delete without device writes", async ({
  page,
}) => {
  await openDisplay(page);
  const name = `library-${Date.now()}`;
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "one-pixel.png",
    mimeType: "image/png",
    buffer: onePixelPng,
  });
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();
  await page.getByLabel("Asset name", { exact: true }).fill(name);
  await page
    .getByRole("button", { name: "Save prepared asset", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: name }),
  ).toBeVisible();
  expect(writes).toHaveLength(0);

  const assetSelect = page.getByLabel("Display asset", { exact: true });
  const option = assetSelect.locator("option", { hasText: name });
  const assetId = await option.getAttribute("value");
  expect(assetId).toBeTruthy();

  await openDisplay(page);
  await page.getByLabel("Still image bank", { exact: true }).selectOption("4");
  const reloadedAssetSelect = page.getByLabel("Display asset", { exact: true });
  await reloadedAssetSelect.selectOption(assetId);
  await page
    .getByRole("button", { name: "Load asset into editor", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({
      hasText: "Upload remains a separate step",
    }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Still image bank", { exact: true }),
  ).toHaveValue("4");
  expect(writes).toHaveLength(0);

  await page.getByRole("button", { name: "Delete asset", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm delete asset", exact: true })
    .click();
  await expect(
    reloadedAssetSelect.locator(`option[value="${assetId}"]`),
  ).toHaveCount(0);
  expect(writes).toHaveLength(0);
});

test("display asset save errors preserve the prepared draft", async ({
  page,
}) => {
  await page.route("**/api/display_asset_save", async (route) => {
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "display storage unavailable" }),
    });
  });
  await openDisplay(page);
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "one-pixel.png",
    mimeType: "image/png",
    buffer: onePixelPng,
  });
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await page.getByLabel("Asset name", { exact: true }).fill("conflict");
  await page
    .getByRole("button", { name: "Save prepared asset", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "display storage unavailable",
  );
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();
});

test("pending and failed asset loads lock actions and preserve the draft", async ({
  page,
}) => {
  await openDisplay(page);
  const name = `load-${Date.now()}`;
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "one-pixel.png",
    mimeType: "image/png",
    buffer: onePixelPng,
  });
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await page.getByLabel("Asset name", { exact: true }).fill(name);
  await page
    .getByRole("button", { name: "Save prepared asset", exact: true })
    .click();
  const assetSelect = page.getByLabel("Display asset", { exact: true });
  const assetId = await assetSelect
    .locator("option", { hasText: name })
    .getAttribute("value");
  let started;
  const startedPromise = new Promise((resolve) => {
    started = resolve;
  });
  let release;
  const responsePromise = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/display_asset_get", async (route) => {
    started();
    await responsePromise;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "display storage unavailable" }),
    });
  });
  await assetSelect.selectOption(assetId);
  await page
    .getByRole("button", { name: "Load asset into editor", exact: true })
    .click();
  await startedPromise;
  await expect(page.getByLabel("Asset name", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Save prepared asset", exact: true }),
  ).toBeDisabled();
  release();
  await expect(page.getByRole("alert")).toContainText(
    "display storage unavailable",
  );
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();
});
