import { test, expect } from "@playwright/test";
test("component versions require an explicit read and clear on reconnect or failed refresh", async ({
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
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const read = page.getByRole("button", {
    name: "Read component versions",
    exact: true,
  });
  await expect(read).toBeEnabled();
  await expect(page.getByText("RF component:", { exact: false })).toHaveCount(
    0,
  );
  const writes = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/write")) writes.push(r);
  });
  await read.click();
  await expect(
    page.getByText("RF component: 4660 (0x1234)", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("MLED component: 1025 (0x0401)", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("OLED component: 770 (0x0302)", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Flash component: 43981 (0xabcd)", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/read", async (route) => {
    if (route.request().postDataJSON().section === "firmware_versions")
      await route.fulfill({
        status: 400,
        json: { error: "version query timed out" },
      });
    else await route.continue();
  });
  await read.click();
  await expect(page.getByRole("alert")).toContainText(
    "version query timed out",
  );
  await expect(page.getByText("RF component:", { exact: false })).toHaveCount(
    0,
  );
  await page.unroute("**/api/read");
  await read.click();
  await expect(
    page.getByText("RF component: 4660 (0x1234)", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("RF component:", { exact: false })).toHaveCount(
    0,
  );
  expect(writes).toHaveLength(0);
});
