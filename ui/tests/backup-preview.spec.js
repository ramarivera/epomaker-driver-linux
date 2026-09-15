import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
async function setup(page, request) {
  await request.post("/api/connect", {
    headers,
    data: { path: "/dev/hidraw-test" },
  });
  const response = await request.post("/api/read", {
    headers,
    data: { section: "backup" },
  });
  expect(response.ok()).toBe(true);
  const snapshot = await response.json();
  await request.post("/api/disconnect", { headers, data: {} });
  const writes = [];
  await page.route("**/api/write", (route) => {
    writes.push(route.request().postDataJSON());
    return route.abort();
  });
  await page.goto("/#token=ui-test-token");
  await page.getByRole("button", { name: "Backups", exact: true }).click();
  return { snapshot, writes };
}
const upload = (page, value) =>
  page.getByLabel("Backup file", { exact: true }).setInputFiles({
    name: "backup.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(value)),
  });
test("offline restore preview reports omitted slots and rejects malformed replacement", async ({
  page,
  request,
}) => {
  const { snapshot, writes } = await setup(page, request);
  delete snapshot.macros["255"];
  await upload(page, snapshot);
  const contents = page.getByRole("note", {
    name: "Backup contents",
    exact: true,
  });
  await expect(contents).toContainText(
    "3 profiles · 255 macro slots · 5 custom color banks",
  );
  await expect(contents).toContainText(
    "snapshot omits 1 macro slot; omitted slots are left unchanged",
  );
  await expect(contents).toContainText("screen pixels are not included");
  await expect(
    page.getByRole("button", { name: "Restore backup", exact: true }),
  ).toBeDisabled();
  await upload(page, { schema_version: 3, identity: { device_id: 3059 } });
  await expect(contents).toHaveCount(0);
  await expect(
    page.getByText("snapshot has missing or malformed fields", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(0);
});
test("pending validation locks file replacement and performs no restore", async ({
  page,
  request,
}) => {
  const { snapshot, writes } = await setup(page, request);
  let held;
  await page.route("**/api/backup_validate", (route) => {
    held = route;
  });
  await upload(page, snapshot);
  await expect.poll(() => Boolean(held)).toBe(true);
  await expect(page.getByLabel("Backup file", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Restore backup", exact: true }),
  ).toBeDisabled();
  await held.fulfill({
    status: 400,
    json: { error: "Invalid backup payload" },
  });
  await expect(page.getByLabel("Backup file", { exact: true })).toBeEnabled();
  await expect(
    page.getByRole("note", { name: "Backup contents", exact: true }),
  ).toHaveCount(0);
  expect(writes).toHaveLength(0);
});
