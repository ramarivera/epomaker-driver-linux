import { test, expect } from "@playwright/test";

async function openRecorder(page) {
  await page.goto("/#token=ui-test-token");
  await page.getByLabel("Device", { exact: true }).selectOption({
    label: "Glyph simulator · bluetooth",
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  const pad = page.getByRole("textbox", {
    name: "Recording area",
    exact: true,
  });
  await expect(pad).toBeFocused();
  return pad;
}

async function useRecording(page) {
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
}

async function stopAndPreview(page) {
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
}

test("records left, right, and middle mouse buttons with readable preview", async ({
  page,
}) => {
  const pad = await openRecorder(page);
  const box = await pad.boundingBox();
  await page.mouse.click(box.x + 30, box.y + 30, { button: "left" });
  await page.mouse.click(box.x + 40, box.y + 30, { button: "right" });
  await page.mouse.click(box.x + 50, box.y + 30, { button: "middle" });
  await stopAndPreview(page);
  await expect(page.getByText("Press Left mouse button")).toBeVisible();
  await expect(page.getByText("Press Right mouse button")).toBeVisible();
  await expect(page.getByText("Press Middle mouse button")).toBeVisible();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
  await expect(
    page.getByLabel("Event 1 mouse button", { exact: true }),
  ).toHaveValue("left");
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("right");
  await expect(
    page.getByLabel("Event 5 mouse button", { exact: true }),
  ).toHaveValue("middle");
});

test("preserves mixed keyboard and mouse order and validates save/readback", async ({
  page,
}) => {
  const pad = await openRecorder(page);
  await page.keyboard.press("a");
  await pad.dispatchEvent("mousedown", { button: 0, buttons: 1 });
  await pad.dispatchEvent("mouseup", { button: 0, buttons: 0 });
  await useRecording(page);
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("left");
  await page.getByRole("button", { name: "Save macro", exact: true }).click();
  await expect(
    page.getByText("Macro readback verified.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New macro", exact: true }).click();
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("left");
});

test("releases held mouse buttons on blur and Escape in reverse order", async ({
  page,
}) => {
  const pad = await openRecorder(page);
  await pad.dispatchEvent("mousedown", { button: 0, buttons: 1 });
  await pad.dispatchEvent("mousedown", { button: 2, buttons: 5 });
  await pad.evaluate((node) => node.blur());
  await expect(page.getByText(/Recorded 4 actions/)).toBeVisible();
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await expect(page.getByText("Release Right mouse button")).toBeVisible();
  await expect(page.getByText("Release Left mouse button")).toBeVisible();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("right");
  await expect(
    page.getByLabel("Event 4 mouse button", { exact: true }),
  ).toHaveValue("left");
});

test("does not capture mouse clicks outside the pad", async ({ page }) => {
  await page.goto("/#token=ui-test-token");
  await page.getByLabel("Device", { exact: true }).selectOption({
    label: "Glyph simulator · bluetooth",
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(page.getByText(/Recorded 0 actions/)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toHaveCount(0);
});
