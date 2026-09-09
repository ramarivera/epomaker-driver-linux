import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const unknownMacro = "0100ff01" + "00".repeat(252);
const emptyMacro = "0100" + "00".repeat(254);

async function openMacros(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
  await page.getByLabel("Device", { exact: true }).selectOption({
    label: "Glyph simulator · bluetooth",
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Macros", exact: true }),
  ).toBeVisible();
}

test("raw export keeps the loaded slot after editing the current slot", async ({
  page,
}) => {
  await openMacros(page);
  await page.route("**/api/read", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        decoded: null,
        data: unknownMacro,
        decode_error: "fixture",
      }),
    }),
  );
  await page.getByLabel("Macro slot", { exact: true }).fill("7");
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(page.getByText(/Raw snapshot from slot 7/)).toBeVisible();
  await page.getByLabel("Macro slot", { exact: true }).fill("12");
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: /Export raw data from slot 7/ })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("macro-7-raw.json");
  expect(JSON.parse(await readFile(await download.path(), "utf8"))).toEqual({
    slot: 7,
    data: unknownMacro,
  });
});

test("slot edits while a read is pending do not relabel the raw snapshot", async ({
  page,
}) => {
  await openMacros(page);
  let readStarted;
  const readStartedPromise = new Promise((resolve) => {
    readStarted = resolve;
  });
  let releaseRead;
  const responsePromise = new Promise((resolve) => {
    releaseRead = resolve;
  });
  await page.route("**/api/read", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      section: "macro",
      slot: 3,
    });
    readStarted();
    await responsePromise;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        decoded: null,
        data: unknownMacro,
        decode_error: "fixture",
      }),
    });
  });
  await page.getByLabel("Macro slot", { exact: true }).fill("3");
  const load = page
    .getByRole("button", { name: "Load macro", exact: true })
    .click();
  await readStartedPromise;
  await page.getByLabel("Macro slot", { exact: true }).fill("19");
  releaseRead();
  await load;
  await expect(
    page.getByRole("button", { name: "Load macro", exact: true }),
  ).toBeEnabled();
  await expect(page.getByText(/Raw snapshot from slot 3/)).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: /Export raw data from slot 3/ })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("macro-3-raw.json");
  expect(JSON.parse(await readFile(await download.path(), "utf8"))).toEqual({
    slot: 3,
    data: unknownMacro,
  });
});

test("New macro and JSON import clear the loaded raw snapshot", async ({
  page,
}) => {
  await openMacros(page);
  await page.route("**/api/read", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        decoded: { repeat: 1, events: [] },
        data: emptyMacro,
      }),
    }),
  );
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Export raw data from slot 0/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New macro", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Export raw data/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Export raw data from slot 0/ }),
  ).toBeVisible();
  await page.getByLabel("Import JSON", { exact: true }).setInputFiles({
    name: "import.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"repeat":1,"events":[]}'),
  });
  await expect(
    page.getByRole("button", { name: /Export raw data/ }),
  ).toHaveCount(0);
});
