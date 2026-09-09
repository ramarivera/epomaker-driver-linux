import { test, expect } from "@playwright/test";

const uniqueName = () => `I${Date.now().toString(36)}`;

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
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Macros", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeEnabled();
}

async function reloadMacros(page) {
  await page.reload();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeEnabled();
}

test("real library API persists, renames, updates, deletes, and never writes the device", async ({
  page,
}) => {
  await openMacros(page);
  const name = uniqueName();
  const renamed = `${name}R`;
  const deviceWrites = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) deviceWrites.push(request);
  });

  await page.getByLabel("Repeat count", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByLabel("Event 1 direction", { exact: true })
    .selectOption("false");
  await page.getByLabel("Library name", { exact: true }).fill(name);
  await page
    .getByLabel("Playback preference", { exact: true })
    .selectOption("held");
  await page
    .getByRole("button", { name: "Save as new library entry", exact: true })
    .click();
  await expect(page.getByText(new RegExp(`Saved “${name}”`))).toBeVisible();

  await reloadMacros(page);
  await page
    .getByLabel("Library entry", { exact: true })
    .selectOption({ label: `${name} · held` });
  page.on("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Load into editor", exact: true })
    .click();
  await expect(page.getByLabel("Repeat count", { exact: true })).toHaveValue(
    "3",
  );
  await expect(
    page.getByLabel("Event 1 direction", { exact: true }),
  ).toHaveValue("false");

  // Rename must preserve the stored sequence and mode even when the editor
  // contains an unsubmitted draft.
  await page.getByLabel("Repeat count", { exact: true }).fill("9");
  await page
    .getByLabel("Playback preference", { exact: true })
    .selectOption("count");
  await page.getByLabel("Library name", { exact: true }).fill(renamed);
  await page
    .getByRole("button", { name: "Rename selected", exact: true })
    .click();
  await expect(
    page.getByText(new RegExp(`Updated “${renamed}”`)),
  ).toBeVisible();
  await reloadMacros(page);
  await expect(
    page.getByRole("option", { name: new RegExp(`${renamed} · held`) }),
  ).toHaveCount(1);
  await page
    .getByLabel("Library entry", { exact: true })
    .selectOption({ label: `${renamed} · held` });
  await page
    .getByRole("button", { name: "Load into editor", exact: true })
    .click();
  await expect(page.getByLabel("Repeat count", { exact: true })).toHaveValue(
    "3",
  );

  await page.getByLabel("Repeat count", { exact: true }).fill("5");
  await page
    .getByLabel("Playback preference", { exact: true })
    .selectOption("toggle");
  await page
    .getByRole("button", { name: "Update selected entry", exact: true })
    .click();
  await expect(
    page.getByText(new RegExp(`Updated “${renamed}”`)),
  ).toBeVisible();
  await reloadMacros(page);
  await expect(
    page.getByRole("option", { name: new RegExp(`${renamed} · toggle`) }),
  ).toHaveCount(1);
  await page
    .getByLabel("Library entry", { exact: true })
    .selectOption({ label: `${renamed} · toggle` });
  await page
    .getByRole("button", { name: "Load into editor", exact: true })
    .click();
  await expect(page.getByLabel("Repeat count", { exact: true })).toHaveValue(
    "5",
  );

  await page
    .getByRole("button", { name: "Delete selected", exact: true })
    .click();
  await reloadMacros(page);
  await expect(
    page.getByRole("option", { name: new RegExp(renamed) }),
  ).toHaveCount(0);
  expect(deviceWrites).toHaveLength(0);
});

test("recording draft locks library actions until it is discarded", async ({
  page,
}) => {
  await openMacros(page);
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", {
      name: "Save as new library entry",
      exact: true,
    }),
  ).toBeDisabled();
  const recordingArea = page.getByRole("textbox", {
    name: "Recording area",
    exact: true,
  });
  await recordingArea.press("a");
  await recordingArea.press("Escape");
  await expect(
    page.getByRole("button", { name: "Discard recording", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Discard recording", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeEnabled();
});

test("pending library save locks editor and recorder actions", async ({
  page,
}) => {
  let saveStarted;
  const saveStartedPromise = new Promise((resolve) => {
    saveStarted = resolve;
  });
  let releaseSave;
  const saveResponse = new Promise((resolve) => {
    releaseSave = resolve;
  });
  await page.route("**/api/macro_library_save", async (route) => {
    saveStarted();
    await saveResponse;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "fedcba9876543210fedcba9876543210",
        revision: 1,
        name: "Pending save",
        mode: "count",
        value: { repeat: 1, events: [] },
      }),
    });
  });
  await openMacros(page);
  for (const viewport of [
    { width: 1265, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    const nameBox = await page
      .getByLabel("Library name", { exact: true })
      .boundingBox();
    const modeBox = await page
      .getByLabel("Playback preference", { exact: true })
      .boundingBox();
    expect(nameBox?.width || 0).toBeGreaterThanOrEqual(120);
    expect(modeBox?.width || 0).toBeGreaterThanOrEqual(120);
  }
  await page.setViewportSize({ width: 1586, height: 992 });
  await page.getByLabel("Library name", { exact: true }).fill("Pending save");
  const save = page
    .getByRole("button", { name: "Save as new library entry", exact: true })
    .click();
  await saveStartedPromise;
  await expect(
    page.getByRole("button", { name: "New macro", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Load macro", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Import JSON", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Start recording", exact: true }),
  ).toBeDisabled();
  releaseSave();
  await save;
  await expect(page.getByText(/Saved “Pending save”/)).toBeVisible();
});
