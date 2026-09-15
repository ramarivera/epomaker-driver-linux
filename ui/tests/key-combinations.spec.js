import { test, expect } from "@playwright/test";

const headers = { "X-Epomaker-Token": "ui-test-token" };

test("two-key combinations retain every modifier bit across device readback", async ({
  page,
  request,
}) => {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page
    .getByLabel("Device", { exact: true })
    .selectOption("/dev/hidraw-test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const apply = page.getByRole("button", {
    name: "Apply to keyboard",
    exact: true,
  });
  await expect(apply).toBeEnabled();
  await page.getByRole("button", { name: "Key A", exact: true }).click();
  await page.getByLabel("Key", { exact: true }).selectOption({ value: "5" });
  await page
    .getByLabel("Second key", { exact: true })
    .selectOption({ value: "6" });
  for (const modifier of [
    "Ctrl",
    "Shift",
    "Alt",
    "Meta",
    "Right Ctrl",
    "Right Shift",
    "Right Alt",
    "Right Meta",
  ]) {
    await page.getByLabel(modifier, { exact: true }).check();
  }
  await apply.click();
  await expect(
    page.getByText("Assignment verified.", { exact: true }),
  ).toBeVisible();
  const catalog = await (await request.get("/api/catalog", { headers })).json();
  const slot = Array.from({ length: 128 }, (_, n) => n).find(
    (n) => catalog.matrices[0].slice(n * 4, n * 4 + 4).join() === "0,0,4,0",
  );
  let read = await (
    await request.post("/api/read", { headers, data: { section: "keymap" } })
  ).json();
  expect(read.raw.slice(slot * 4, slot * 4 + 4)).toEqual([0, 255, 5, 6]);
  await page.getByRole("button", { name: "Key S", exact: true }).click();
  await page.getByRole("button", { name: "Key A", exact: true }).click();
  await expect(page.getByLabel("Second key", { exact: true })).toHaveValue("6");
  await expect(page.getByLabel("Right Alt", { exact: true })).toBeChecked();
  await page.getByLabel("Right Alt", { exact: true }).uncheck();
  await page
    .getByLabel("Second key", { exact: true })
    .selectOption({ value: "0" });
  await apply.click();
  await expect(apply).toBeEnabled();
  read = await (
    await request.post("/api/read", { headers, data: { section: "keymap" } })
  ).json();
  expect(read.raw.slice(slot * 4, slot * 4 + 4)).toEqual([0, 191, 5, 0]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Right Meta", { exact: true }).uncheck();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
