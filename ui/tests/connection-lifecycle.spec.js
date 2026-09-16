import { test, expect } from "@playwright/test";

test("polling reflects a keyboard disappearing and returning", async ({
  page,
}) => {
  let connected = true;
  let present = true;
  await page.route("**/api/devices", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        present
          ? [{ path: "/dev/glyph", name: "Glyph", command_transport: "usb" }]
          : [],
      ),
    }),
  );
  await page.route("**/api/connection", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        connected ? { model: "Epomaker Glyph", path: "/dev/glyph" } : null,
      ),
    }),
  );
  await page.route("**/api/catalog", (route) => route.continue());
  await page.goto("/#token=ui-test-token");
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await page
    .getByRole("combobox", { name: "Device", exact: true })
    .selectOption("/dev/glyph");
  connected = false;
  present = false;
  await expect(
    page.getByText("Keyboard connection lost.", { exact: true }),
  ).toBeVisible({ timeout: 5000 });
  await expect(
    page.getByRole("combobox", { name: "Device", exact: true }),
  ).toHaveValue("");
  present = true;
  await expect(
    page.getByRole("combobox", { name: "Device", exact: true }),
  ).toContainText("Glyph · usb", { timeout: 5000 });
  await expect(
    page.getByText("Offline preview", { exact: true }),
  ).toBeVisible();
});

test("refresh devices also refreshes connection state", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/devices", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/connection", (route) => {
    calls += 1;
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(null),
    });
  });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const before = calls;
  await page
    .getByRole("button", { name: "Refresh devices", exact: true })
    .click();
  await expect.poll(() => calls).toBeGreaterThan(before);
});

test("an old disconnected poll cannot replace a new connection", async ({
  page,
}) => {
  let release;
  let delayed = false;
  let settled = false;
  let calls = 0;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/connection", async (route) => {
    const callNumber = ++calls;
    // Keep only bootstrap and the held stale poll mocked; later reads must
    // observe the new backend session, including explicit Refresh devices.
    if (callNumber > 2) {
      await route.continue();
      return;
    }
    const held = callNumber === 2;
    if (held) {
      delayed = true;
      await waiting;
    }
    await route.fulfill({ contentType: "application/json", body: "null" });
    if (held) settled = true;
  });
  await page.goto("/#token=ui-test-token");
  await page
    .getByRole("combobox", { name: "Device", exact: true })
    .selectOption("/dev/hidraw-test");
  await expect.poll(() => delayed).toBe(true);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  // Future polls use the real backend's current session; only the held poll is stale.
  release();
  await expect.poll(() => settled).toBe(true);
  await expect(
    page.getByText("Keyboard connection lost.", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Refresh devices", exact: true })
    .click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
});

test("poll failures are visible without inventing a disconnect", async ({
  page,
}) => {
  let fail = false;
  await page.route("**/api/connection", async (route) => {
    if (fail)
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ message: "sysfs unavailable" }),
      });
    else await route.continue();
  });
  await page.goto("/#token=ui-test-token");
  await page
    .getByRole("combobox", { name: "Device", exact: true })
    .selectOption("/dev/hidraw-test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  fail = true;
  await expect(page.getByRole("alert")).toContainText(
    "Connection status unavailable",
    { timeout: 5000 },
  );
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
});

test("a delayed device list cannot clear a newer selection", async ({
  page,
}) => {
  let calls = 0;
  let held = false;
  let release;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/devices", async (route) => {
    calls += 1;
    if (calls === 2) {
      held = true;
      await waiting;
      await route.fulfill({ contentType: "application/json", body: "[]" });
    } else await route.continue();
  });
  await page.goto("/#token=ui-test-token");
  const select = page.getByRole("combobox", { name: "Device", exact: true });
  await select.selectOption("/dev/hidraw-test");
  await expect.poll(() => held).toBe(true);
  await select.selectOption("/dev/hidraw-usb-test");
  release();
  await expect.poll(() => calls).toBeGreaterThan(2);
  await expect(select).toHaveValue("/dev/hidraw-usb-test");
});
