import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
async function open(page, request) {
  await request.post("/api/system_info_refresh_stop", { headers, data: {} });
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
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Start system information refresh",
      exact: true,
    }),
  ).toBeEnabled();
}
test("system information refresh continues across navigation and stops explicitly", async ({
  page,
  request,
}) => {
  await open(page, request);
  await page
    .getByLabel("Refresh interval (seconds)", { exact: true })
    .fill("1");
  await page
    .getByRole("button", {
      name: "Start system information refresh",
      exact: true,
    })
    .click();
  await expect(
    page.getByText(
      /System information refresh running · [1-9]\d* samples sent/,
    ),
  ).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel("Disk path", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await expect(
    page.getByText(/System information refresh running/),
  ).toBeVisible();
  await expect(
    page.getByLabel("Refresh interval (seconds)", { exact: true }),
  ).toHaveValue("1");
  await page
    .getByRole("button", {
      name: "Stop system information refresh",
      exact: true,
    })
    .click();
  await expect(
    page.getByText(/System information refresh stopped/),
  ).toBeVisible();
  const status = await (
    await request.get("/api/system_info_refresh", { headers })
  ).json();
  expect(status.running).toBe(false);
  expect(status.samples).toBeGreaterThan(0);
});
test("disconnect stops refresh and reconnect does not restart it", async ({
  page,
  request,
}) => {
  await open(page, request);
  await page
    .getByRole("button", {
      name: "Start system information refresh",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Stop system information refresh",
      exact: true,
    }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByText(/System information refresh stopped/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Start system information refresh",
      exact: true,
    }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Start system information refresh",
      exact: true,
    }),
  ).toBeEnabled();
  expect(
    (await (await request.get("/api/system_info_refresh", { headers })).json())
      .running,
  ).toBe(false);
});
