import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const onePixelPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function seedAsset(request, name) {
  const response = await request.post("/api/display_asset_save", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: {
      name,
      kind: "screen",
      delay_ms: null,
      content: onePixelPng.toString("base64"),
    },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

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

test("display asset export/import is portable and leaves editor draft unchanged", async ({
  page,
  request,
}) => {
  const sourceName = `portable-${Date.now()}`;
  const source = await seedAsset(request, sourceName);
  const writes = [];
  page.on("request", (requestEvent) => {
    if (requestEvent.url().endsWith("/api/write")) writes.push(requestEvent);
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
  await page.getByLabel("Still image bank", { exact: true }).selectOption("4");
  await page
    .getByLabel("Display asset", { exact: true })
    .selectOption(source.id);
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export display asset JSON", exact: true })
    .click();
  const download = await downloadPromise;
  const exported = JSON.parse(await readFile(await download.path(), "utf8"));
  expect(exported).toEqual({
    schema: "epomaker-glyph-display-asset",
    version: 1,
    model_id: 3059,
    name: source.name,
    kind: source.kind,
    delay_ms: source.delay_ms,
    content: onePixelPng.toString("base64"),
  });
  expect(exported.id).toBeUndefined();
  expect(exported.preview_png).toBeUndefined();

  const portableFile = {
    name: "portable.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(exported)),
  };
  const importer = page.getByLabel("Import display asset JSON", {
    exact: true,
  });
  await importer.setInputFiles(portableFile);
  await expect(
    page.getByLabel("Display asset", { exact: true }),
  ).not.toHaveValue(source.id);
  const firstImportedId = await page
    .getByLabel("Display asset", { exact: true })
    .inputValue();
  await importer.setInputFiles(portableFile);
  await expect(
    page.getByLabel("Display asset", { exact: true }),
  ).not.toHaveValue(firstImportedId);
  const secondImportedId = await page
    .getByLabel("Display asset", { exact: true })
    .inputValue();
  expect(firstImportedId).not.toBe(source.id);
  expect(secondImportedId).not.toBe(source.id);
  expect(secondImportedId).not.toBe(firstImportedId);
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();
  await expect(
    page.getByLabel("Still image bank", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByText("Source: one-pixel.png", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(0);

  for (const id of [source.id, firstImportedId, secondImportedId])
    await request.post("/api/display_asset_delete", {
      headers: { "X-Epomaker-Token": "ui-test-token" },
      data: { id },
    });
});

test("malformed, oversized, and rejected display imports preserve list and draft", async ({
  page,
  request,
}) => {
  const source = await seedAsset(request, `reject-${Date.now()}`);
  await openDisplay(page);
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "one-pixel.png",
    mimeType: "image/png",
    buffer: onePixelPng,
  });
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  const assetSelect = page.getByLabel("Display asset", { exact: true });
  await assetSelect.selectOption(source.id);
  const importer = page.getByLabel("Import display asset JSON", {
    exact: true,
  });
  await importer.setInputFiles({
    name: "malformed.json",
    mimeType: "application/json",
    buffer: Buffer.from("{not json"),
  });
  await expect(page.getByRole("alert")).toContainText("not valid JSON");
  await expect(assetSelect).toHaveValue(source.id);
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();

  await page.route("**/api/display_asset_import", async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ error: "display asset rejected" }),
    });
  });
  await importer.setInputFiles({
    name: "rejected.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        schema: "epomaker-glyph-display-asset",
        version: 1,
        model_id: 3059,
        name: source.name,
        kind: source.kind,
        delay_ms: source.delay_ms,
        content: onePixelPng.toString("base64"),
      }),
    ),
  });
  await expect(page.getByRole("alert")).toContainText("display asset rejected");
  await expect(assetSelect).toHaveValue(source.id);
  await expect(
    page.getByAltText("Prepared display pixels, first frame"),
  ).toBeVisible();

  await importer.setInputFiles({
    name: "oversized.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(20 * 1024 * 1024 + 1, 120),
  });
  await expect(page.getByRole("alert")).toContainText("20 MiB");
  await expect(assetSelect).toHaveValue(source.id);
  await request.post("/api/display_asset_delete", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: { id: source.id },
  });
});
