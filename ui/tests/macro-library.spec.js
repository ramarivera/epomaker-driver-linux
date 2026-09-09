import { test, expect } from "@playwright/test";

const id = "0123456789abcdef0123456789abcdef";
const stored = {
  id,
  revision: 4,
  name: "Stored macro",
  mode: "toggle",
  value: { repeat: 1, events: [{ hid_usage: 4, down: true, delay_ms: 10 }] },
};

test("library loads explicitly, saves metadata without device writes, renames and deletes", async ({
  page,
}) => {
  let entry = { ...stored };
  await page.route("**/api/macro_library", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ entries: [entry] }),
    }),
  );
  await page.route("**/api/macro_library_save", async (route) => {
    const payload = route.request().postDataJSON();
    entry = { ...entry, ...payload, revision: entry.revision + 1 };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(entry),
    });
  });
  await page.route("**/api/macro_library_delete", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(page.getByRole("option", { name: /Stored macro/ })).toHaveCount(
    1,
  );

  await page.getByLabel("Macro slot", { exact: true }).fill("9");
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByLabel("Library entry", { exact: true }).selectOption(id);
  await page
    .getByRole("button", { name: "Load into editor", exact: true })
    .click();
  await expect(page.getByLabel("Macro slot", { exact: true })).toHaveValue("9");
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");

  await page.getByLabel("Library name", { exact: true }).fill("");
  await page
    .getByRole("button", { name: "Save as new library entry", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("nonempty");
  await page.getByLabel("Library name", { exact: true }).fill("Renamed macro");
  await page
    .getByRole("button", { name: "Rename selected", exact: true })
    .click();
  await expect(page.getByText(/Updated “Renamed macro”/)).toBeVisible();
  expect(writes).toHaveLength(0);

  await page.reload();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(page.getByRole("option", { name: /Renamed macro/ })).toHaveCount(
    1,
  );
  await page.getByLabel("Library entry", { exact: true }).selectOption(id);

  await page
    .getByRole("button", { name: "Delete selected", exact: true })
    .click();
  await expect(
    page.getByText(/device macro slot was not changed/),
  ).toBeVisible();
});

test("revision conflict preserves the current editor draft", async ({
  page,
}) => {
  await page.route("**/api/macro_library", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ entries: [stored] }),
    }),
  );
  await page.route("**/api/macro_library_save", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "macro library revision conflict" }),
    }),
  );
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await page.getByLabel("Library entry", { exact: true }).selectOption(id);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByRole("button", { name: "Update selected entry", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("revision conflict");
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
});
