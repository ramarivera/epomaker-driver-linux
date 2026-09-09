import { test, expect } from "@playwright/test";

async function openMacros(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeEnabled();
}

test("pair insertion rejects overflow without truncating a full macro", async ({
  page,
}) => {
  await openMacros(page);
  const full = {
    repeat: 2,
    events: Array.from({ length: 127 }, () => ({
      hid_usage: 4,
      down: false,
      delay_ms: 1,
    })),
  };
  await page.getByLabel("Import JSON", { exact: true }).setInputFiles({
    name: "full.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(full)),
  });
  await expect(
    page.getByLabel("Event 127 key usage", { exact: true }),
  ).toHaveValue("4");
  await page
    .getByRole("button", { name: "Capture key/button pair", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Event capture area", exact: true })
    .press("b");
  await page.getByRole("button", { name: "Apply pair", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "macro exceeds 256-byte storage",
  );
  await expect(page.getByLabel("Repeat count", { exact: true })).toHaveValue(
    "2",
  );
  await expect(
    page.getByLabel("Event 127 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByLabel("Event 128 key usage", { exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Add event", exact: true }),
  ).toBeEnabled();
});

test("pending pair validation prevents duplicate application and preserves draft on failure", async ({
  page,
}) => {
  await openMacros(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  let started, finish;
  const entered = new Promise((resolve) => {
    started = resolve;
  });
  const released = new Promise((resolve) => {
    finish = resolve;
  });
  let requests = 0;
  await page.route("**/api/validate_macro", async (route) => {
    requests++;
    started();
    await released;
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "validation unavailable" }),
    });
  });
  await page
    .getByRole("button", { name: "Capture key/button pair", exact: true })
    .click();
  const area = page.getByRole("textbox", {
    name: "Event capture area",
    exact: true,
  });
  await area.press("b");
  await page.getByRole("button", { name: "Apply pair", exact: true }).click();
  await entered;
  await expect(
    page.getByRole("button", { name: "Validating…", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "New macro", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Refresh library", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Repeat count", { exact: true })).toBeDisabled();
  await area.press("Escape");
  await expect(page.getByRole("dialog")).toBeVisible();
  finish();
  await expect(page.getByRole("alert")).toContainText("validation unavailable");
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByLabel("Event 2 key usage", { exact: true }),
  ).toHaveCount(0);
  expect(requests).toBe(1);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
});

test("keyboard users can tab from the preview to Apply, and outside focus cancels", async ({
  page,
}) => {
  await openMacros(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Event capture area", exact: true })
    .press("b");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Apply captured input", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("5");
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Event capture area", exact: true })
    .press("c");
  await page.getByLabel("Device", { exact: true }).focus();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("5");
});
