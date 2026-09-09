import { test, expect } from "@playwright/test";

async function record(page) {
  await page.goto("/#token=ui-test-token");
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  const area = page.getByRole("textbox", {
    name: "Recording area",
    exact: true,
  });
  await expect(area).toBeFocused();
  return area;
}
async function accept(page) {
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
}

test("release outside the area precedes subsequent keys without a synthetic release", async ({
  page,
}) => {
  const area = await record(page);
  const box = await area.boundingBox();
  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(1, 1);
  await page.mouse.up();
  await page.keyboard.press("a");
  await page.keyboard.press("Escape");
  await expect(page.getByText(/Recorded 4 actions/)).toBeVisible();
  await expect(page.getByRole("note")).toHaveCount(0);
  await accept(page);
  await expect(
    page.getByLabel("Event 2 mouse button", { exact: true }),
  ).toHaveValue("left");
  await expect(
    page.getByLabel("Event 2 direction", { exact: true }),
  ).toHaveValue("false");
  await expect(
    page.getByLabel("Event 3 key usage", { exact: true }),
  ).toHaveValue("4");
});

test("back and forward DOM buttons are mapped and their default actions canceled", async ({
  page,
}) => {
  const area = await record(page);
  for (const button of [3, 4]) {
    // Playwright's real mouse API only supports left/right/middle. This checks
    // the extra-button DOM mapping and cancellation, not physical navigation.
    const canceled = await area.evaluate((node, button) => {
      const event = new MouseEvent("mousedown", {
        button,
        bubbles: true,
        cancelable: true,
      });
      node.dispatchEvent(event);
      return event.defaultPrevented;
    }, button);
    expect(canceled).toBe(true);
    await area.dispatchEvent("mouseup", {
      button,
      bubbles: true,
      cancelable: true,
    });
  }
  await page.keyboard.press("Escape");
  await accept(page);
  await expect(
    page.getByLabel("Event 1 mouse button", { exact: true }),
  ).toHaveValue("back");
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("forward");
});

test("Escape releases mixed held inputs in reverse order", async ({ page }) => {
  const area = await record(page);
  await page.keyboard.down("Control");
  await area.dispatchEvent("mousedown", { button: 2, buttons: 2 });
  await page.keyboard.press("Escape");
  await page.keyboard.up("Control");
  await expect(page.getByRole("note")).toContainText("Added 2 release actions");
  await accept(page);
  await expect(
    page.getByLabel("Event 3 mouse button", { exact: true }),
  ).toHaveValue("right");
  await expect(
    page.getByLabel("Event 3 direction", { exact: true }),
  ).toHaveValue("false");
  await expect(
    page.getByLabel("Event 4 key usage", { exact: true }),
  ).toHaveValue("224");
  await expect(
    page.getByLabel("Event 4 direction", { exact: true }),
  ).toHaveValue("false");
});

test("unknown mouse buttons invalidate the draft instead of being silently omitted", async ({
  page,
}) => {
  const area = await record(page);
  await page.keyboard.press("a");
  await area.dispatchEvent("mousedown", { button: 6 });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alert")).toContainText(
    "Unsupported mouse button",
  );
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toBeDisabled();
});
