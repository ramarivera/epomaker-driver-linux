import { test, expect } from "@playwright/test";

test("shows Bluetooth telemetry updates and clears it for USB or disconnect", async ({
  page,
}) => {
  let connection = {
    model: "Epomaker Glyph",
    path: "/dev/glyph",
    transport: "bluetooth",
    telemetry: {
      battery_raw: 66,
      battery_age_seconds: 4.9,
      online: true,
      online_age_seconds: 2.2,
    },
  };
  await page.route("**/api/devices", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        { path: "/dev/glyph", name: "Glyph", command_transport: "bluetooth" },
      ]),
    }),
  );
  await page.route("**/api/connection", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(connection),
    }),
  );
  await page.route("**/api/catalog", (route) => route.continue());
  await page.goto("/#token=ui-test-token");

  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Last battery report: 66% · 4 s ago", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Last device status: Online · 2 s ago", { exact: true }),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Refresh devices", exact: true })
    .click();
  const batteryBox = await page
    .getByText("Last battery report: 66% · 4 s ago", { exact: true })
    .boundingBox();
  const statusBox = await page
    .getByText("Last device status: Online · 2 s ago", { exact: true })
    .boundingBox();
  expect(statusBox.y).toBeGreaterThanOrEqual(batteryBox.y + batteryBox.height);
  expect(statusBox.x + statusBox.width).toBeLessThanOrEqual(390);

  connection = {
    ...connection,
    telemetry: {
      battery_raw: 66,
      battery_age_seconds: 8,
      online: false,
      online_age_seconds: 3.9,
    },
  };
  await expect(
    page.getByText("Last device status: Offline · 3 s ago", { exact: true }),
  ).toBeVisible({ timeout: 5000 });
  await expect(
    page.getByText("Last battery report: 66% · 8 s ago", { exact: true }),
  ).toBeVisible();

  connection = { ...connection, transport: "usb" };
  await expect(
    page.getByText("Last battery report: 66% · 8 s ago", { exact: true }),
  ).toHaveCount(0, { timeout: 5000 });
  await expect(
    page.getByText("Last device status: Offline · 3 s ago", { exact: true }),
  ).toHaveCount(0, { timeout: 5000 });

  connection = null;
  await expect(page.getByText("Offline preview", { exact: true })).toBeVisible({
    timeout: 5000,
  });
  await expect(
    page.getByLabel("Device telemetry", { exact: true }),
  ).toHaveCount(0);
});

test("rejects invalid battery values and unknown status ages", async ({
  page,
}) => {
  await page.route("**/api/devices", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/connection", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        model: "Epomaker Glyph",
        transport: "bluetooth",
        telemetry: {
          battery_raw: 255,
          battery_age_seconds: 1,
          online: null,
          online_age_seconds: 1,
        },
      }),
    }),
  );
  await page.route("**/api/catalog", (route) => route.continue());
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByText("Battery: Not reported", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Device status: Not reported", { exact: true }),
  ).toBeVisible();
});
