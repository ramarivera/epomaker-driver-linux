import { test, expect } from "@playwright/test";

const id = "glyph-config-1";
const matrix = "00".repeat(512);
let entry = {
  id,
  revision: 2,
  name: "Quiet Glyph",
  model_id: 3059,
  matrix,
  layer: "Main",
};

async function openKeymap(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Named Glyph key configurations",
      exact: true,
    }),
  ).toBeVisible();
}

test("saves, previews, renames, and deletes a local Glyph configuration", async ({
  page,
}) => {
  await page.route("**/api/config_library", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ entries: [entry] }),
    }),
  );
  await page.route("**/api/config_library_save", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload.matrix).toMatch(/^[0-9a-f]{1024}$/i);
    entry = { ...entry, ...payload, revision: entry.revision + 1 };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(entry),
    });
  });
  await page.route("**/api/config_library_delete", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    }),
  );
  await openKeymap(page);
  await page
    .getByLabel("Configuration name", { exact: true })
    .fill("Saved current");
  await page
    .getByRole("button", { name: "Save current configuration", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Saved");
  await page.getByLabel("Configuration", { exact: true }).selectOption(id);
  await page.getByRole("button", { name: "Load preview", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Previewing");
  await page
    .getByLabel("Configuration name", { exact: true })
    .fill("Renamed Glyph");
  await page
    .getByRole("button", { name: "Rename selected", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Updated");
  await page
    .getByRole("button", { name: "Delete selected", exact: true })
    .click();
  await expect(
    page.getByText("Configuration deleted", { exact: false }),
  ).toBeVisible();
});

test("disables preview and apply when the selected configuration layer differs", async ({
  page,
}) => {
  await page.route("**/api/config_library", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ entries: [{ ...entry, layer: "Fn Mac" }] }),
    }),
  );
  await openKeymap(page);
  await page.getByLabel("Configuration", { exact: true }).selectOption(id);
  await expect(
    page.getByRole("button", { name: "Load preview", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", {
      name: "Apply saved configuration",
      exact: true,
    }),
  ).toBeDisabled();
});

test("apply locks the target, reports failure, then verifies the selected profile", async ({
  page,
  request,
}) => {
  const headers = { "X-Epomaker-Token": "ui-test-token" };
  await request.post("/api/disconnect", { headers, data: {} });
  const response = await request.post("/api/config_library_save", {
    headers,
    data: { name: "Apply test", matrix, layer: "Main" },
  });
  expect(response.ok()).toBe(true);
  const saved = await response.json();
  await openKeymap(page);
  await page
    .getByLabel("Device", { exact: true })
    .selectOption("/dev/hidraw-test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByLabel("Profile", { exact: true })).toBeEnabled();
  await page.getByLabel("Profile", { exact: true }).selectOption("2");
  await page
    .getByLabel("Configuration", { exact: true })
    .selectOption(saved.id);
  let held;
  await page.route("**/api/write", (route) => {
    held = route;
  });
  const apply = page.getByRole("button", {
    name: "Apply saved configuration",
    exact: true,
  });
  await apply.click();
  await expect.poll(() => Boolean(held)).toBe(true);
  expect(held.request().postDataJSON()).toEqual({
    kind: "config",
    id: saved.id,
    revision: saved.revision,
    profile: 2,
  });
  await expect(page.getByLabel("Profile", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Fn Mac", exact: true }),
  ).toBeDisabled();
  await held.fulfill({
    status: 400,
    json: { error: "Simulated write failure" },
  });
  await expect(page.getByRole("alert").first()).toContainText(
    "Simulated write failure",
  );
  await expect(page.getByText(/Applied “/)).toHaveCount(0);
  await expect(apply).toBeEnabled();
  await page.unroute("**/api/write");
  await apply.click();
  await expect(page.getByText(/Applied “Apply test”/)).toBeVisible();
  const read = await request.post("/api/read", {
    headers,
    data: { section: "keymap", profile: 2 },
  });
  expect((await read.json()).raw).toEqual(Array(512).fill(0));
  await expect(page.getByRole("alert")).toHaveCount(0);
});
