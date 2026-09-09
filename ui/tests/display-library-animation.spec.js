import { test, expect } from "@playwright/test";
test("retained animation can be re-prepared with a new delay", async ({
  page,
  request,
}) => {
  const response = await request.post("/api/display_asset_save", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: {
      name: "Retained timing",
      kind: "animation",
      delay_ms: 0,
      content:
        "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAEAAAALAAAAAACAAIAAAgGAAEIBBAQACH5BAEIAAEALAAAAAACAAIAgQAA/wAAAAAAAAAAAAgGAAEIBBAQADs=",
    },
  });
  expect(response.ok()).toBeTruthy();
  const entry = await response.json();
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await expect(page.getByLabel("Display asset", { exact: true })).toBeEnabled();
  await page
    .getByLabel("Display asset", { exact: true })
    .selectOption(entry.id);
  await page
    .getByRole("button", { name: "Load asset into editor", exact: true })
    .click();
  await expect(
    page.getByText("2 frames · 243,104 pixel bytes · 0 ms per frame", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Source: Retained timing", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Frame delay (ms, optional)", { exact: true })
    .fill("120");
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, first frame",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(
    page.getByText("2 frames · 243,104 pixel bytes · 120 ms per frame", {
      exact: true,
    }),
  ).toBeVisible();
  const stored = await request.post("/api/display_asset_get", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: { id: entry.id },
  });
  expect((await stored.json()).delay_ms).toBe(0);
  await request.post("/api/display_asset_delete", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: { id: entry.id },
  });
});
