import { test, expect } from "@playwright/test";
import { deflateRawSync } from "node:zlib";
import { createHash } from "node:crypto";

async function openSettings(page) {
  await page.route("**/api/devices", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/connection", (route) =>
    route.fulfill({ contentType: "application/json", body: "null" }),
  );
  await page.route("**/api/catalog", (route) => route.continue());
  await page.goto("/#token=ui-test-token");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Firmware file inspection" }),
  ).toBeVisible();
}

test("inspects a local firmware file while disconnected and checks metadata explicitly", async ({
  page,
}) => {
  await openSettings(page);
  let inspected;
  let metadataCalls = 0;
  await page.route("**/api/firmware_inspect", async (route) => {
    inspected = route.request().postDataJSON();
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version: inspected.version,
        components: { main: { length: 65537, sha256: "abc123" } },
        structural_only: true,
        write_ready: false,
        model_applicability: "unverified",
        authenticity_verified: false,
        comparison: {
          version: "usbv101",
          candidates: [
            {
              component: "usb",
              observed: 257,
              current: 256,
              candidate: true,
              reason: "available",
            },
          ],
        },
      }),
    });
  });
  await page.route("**/api/firmware_metadata", (route) => {
    metadataCalls += 1;
    return metadataCalls === 1
      ? route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            requested_model_id: 3059,
            version_str: "usbv101",
            file_path: "vendor/fw.bin",
          }),
        })
      : route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({
            error: "metadata unavailable; availability is unknown",
          }),
        });
  });
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "fw.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("synthetic firmware"),
  });
  await page.getByLabel("Vendor version", { exact: true }).fill("usbv101");
  await page
    .getByRole("button", { name: "Inspect local firmware", exact: true })
    .click();
  await expect(
    page.getByText("USB main: 65537 bytes · SHA-256 abc123", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/USB: Candidate · observed 257 · current 256/),
  ).toBeVisible();
  expect(inspected.version).toBe("usbv101");
  expect(Buffer.from(inspected.content, "base64").toString()).toBe(
    "synthetic firmware",
  );
  await expect(
    page.getByText("Vendor version: usbv101", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Check vendor firmware metadata",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Vendor version: usbv101", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Check vendor firmware metadata",
      exact: true,
    })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "availability is unknown",
  );
  await expect(
    page.getByText("Vendor version: usbv101", { exact: true }),
  ).toHaveCount(0);
});

test("ignores a stale reply after version changes", async ({ page }) => {
  await openSettings(page);
  let release;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/firmware_inspect", async (route) => {
    await waiting;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version: "old-version",
        components: { main: { length: 1, sha256: "old" } },
      }),
    });
  });
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "old.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("old"),
  });
  await page.getByLabel("Vendor version", { exact: true }).fill("old-version");
  await page
    .getByRole("button", { name: "Inspect local firmware", exact: true })
    .click();
  const response = page.waitForResponse("**/api/firmware_inspect");
  await page.getByLabel("Vendor version", { exact: true }).fill("new-version");
  release();
  await response;
  await expect(
    page.getByRole("button", { name: "Inspect local firmware", exact: true }),
  ).toBeEnabled();
  await expect(page.getByText("old-version", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Structural inspection only.", { exact: false }),
  ).toHaveCount(0);
});

test("reports oversized local files before inspection", async ({ page }) => {
  await openSettings(page);
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "too-large.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(32 * 1024 * 1024 + 1),
  });
  await expect(page.getByRole("alert")).toHaveText(
    "Firmware file must be 32 MiB or smaller",
  );
});

test("inspects a synthetic raw image through the real backend", async ({
  page,
}) => {
  await openSettings(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const image = Buffer.concat([Buffer.alloc(65536), Buffer.from("glyph")]);
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "x".repeat(180) + ".bin",
    mimeType: "application/octet-stream",
    buffer: deflateRawSync(image),
  });
  await page.getByLabel("Vendor version", { exact: true }).fill("usbv101");
  await page
    .getByRole("button", { name: "Inspect local firmware", exact: true })
    .click();
  await expect(
    page.getByText(
      `USB main: 65541 bytes · SHA-256 ${createHash("sha256").update(image).digest("hex")}`,
      { exact: true },
    ),
  ).toBeVisible();
  expect(
    await page
      .locator(".firmware-inspection")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
});

test("compares real simulator versions and clears the comparison on reread", async ({
  page,
}) => {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph USB simulator · usb" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const read = page.getByRole("button", {
    name: "Read component versions",
    exact: true,
  });
  await read.click();
  await expect(
    page.getByText("RF component: 4660 (0x1234)", { exact: true }),
  ).toBeVisible();
  const image = Buffer.concat([Buffer.alloc(65536), Buffer.from("glyph")]);
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "fw.bin",
    mimeType: "application/octet-stream",
    buffer: deflateRawSync(image),
  });
  await page.getByLabel("Vendor version", { exact: true }).fill("usbv101");
  const sent = page.waitForRequest("**/api/firmware_inspect");
  await page
    .getByRole("button", { name: "Inspect local firmware", exact: true })
    .click();
  expect((await sent).postDataJSON().current_versions).toEqual({
    usb: null,
    rf: 4660,
    mled: 1025,
    oled: 770,
    flash: 43981,
  });
  await expect(
    page.getByLabel("Firmware version comparison", { exact: true }),
  ).toContainText("Current device version unknown");
  await read.click();
  await expect(
    page.getByLabel("Firmware version comparison", { exact: true }),
  ).toHaveCount(0);
  await disconnect.click();
});

test("failed repeat inspection clears old success", async ({ page }) => {
  await openSettings(page);
  const image = Buffer.concat([Buffer.alloc(65536), Buffer.from("glyph")]);
  await page.getByLabel("Local firmware file", { exact: true }).setInputFiles({
    name: "fw.bin",
    mimeType: "application/octet-stream",
    buffer: deflateRawSync(image),
  });
  await page.getByLabel("Vendor version", { exact: true }).fill("usbv101");
  const inspect = page.getByRole("button", {
    name: "Inspect local firmware",
    exact: true,
  });
  await inspect.click();
  await expect(
    page.getByLabel("Firmware inspection result", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/firmware_inspect", (route) =>
    route.fulfill({
      status: 400,
      json: { error: "Could not inspect firmware" },
    }),
  );
  await inspect.click();
  await expect(page.getByRole("alert")).toContainText(
    "Could not inspect firmware",
  );
  await expect(
    page.getByLabel("Firmware inspection result", { exact: true }),
  ).toHaveCount(0);
});
