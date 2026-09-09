import { test, expect } from "@playwright/test";

async function openEditor(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Macros", exact: true }),
  ).toBeVisible();
}

test("captures a modifier for one row and preserves direction and delay", async ({
  page,
}) => {
  await openEditor(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByLabel("Event 1 direction", { exact: true })
    .selectOption("false");
  await page.getByLabel("Event 1 delay", { exact: true }).fill("77");
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Event capture area", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Shift");
  await expect(
    page.getByText("Preview: Shift Left", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Apply captured input", exact: true })
    .click();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("225");
  await expect(
    page.getByLabel("Event 1 direction", { exact: true }),
  ).toHaveValue("false");
  await expect(page.getByLabel("Event 1 delay", { exact: true })).toHaveValue(
    "77",
  );
});

test("converts a keyboard row to a mouse button while preserving row settings", async ({
  page,
}) => {
  await openEditor(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page.getByLabel("Event 1 delay", { exact: true }).fill("88");
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  const area = page.getByRole("textbox", {
    name: "Event capture area",
    exact: true,
  });
  await area.click({ button: "right" });
  await expect(
    page.getByText("Preview: Right mouse button", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Apply captured input", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "Mouse Button", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Event 1 mouse button", { exact: true }),
  ).toHaveValue("right");
  await expect(
    page.getByLabel("Event 1 direction", { exact: true }),
  ).toHaveValue("true");
  await expect(page.getByLabel("Event 1 delay", { exact: true })).toHaveValue(
    "88",
  );
});

test("unknown input can be retried and cancel or Escape leaves the row unchanged", async ({
  page,
}) => {
  await openEditor(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  const area = page.getByRole("textbox", {
    name: "Event capture area",
    exact: true,
  });
  await area.evaluate((node) =>
    node.dispatchEvent(
      new KeyboardEvent("keydown", {
        code: "UnknownKey",
        bubbles: true,
        cancelable: true,
      }),
    ),
  );
  await expect(page.getByRole("alert")).toContainText(
    "Unsupported physical key code",
  );
  await page.keyboard.press("a");
  await expect(page.getByText("Preview: A", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await page
    .getByRole("button", { name: "Capture event 1", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
});

test("captures a validated key/button pair, preserves slot and repeat, and locks editor actions", async ({
  page,
}) => {
  await openEditor(page);
  await page.getByLabel("Macro slot", { exact: true }).fill("17");
  await page.getByLabel("Repeat count", { exact: true }).fill("4");
  await page
    .getByRole("button", { name: "Capture key/button pair", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Add event", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Start recording", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("textbox", { name: "Event capture area", exact: true })
    .focus();
  await page.keyboard.press("b");
  await page.getByLabel("Pair delay", { exact: true }).fill("33");
  await page.getByRole("button", { name: "Apply pair", exact: true }).click();
  await expect(page.getByLabel("Macro slot", { exact: true })).toHaveValue(
    "17",
  );
  await expect(page.getByLabel("Repeat count", { exact: true })).toHaveValue(
    "4",
  );
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("5");
  await expect(
    page.getByLabel("Event 2 key usage", { exact: true }),
  ).toHaveValue("5");
  await expect(
    page.getByLabel("Event 1 direction", { exact: true }),
  ).toHaveValue("true");
  await expect(
    page.getByLabel("Event 2 direction", { exact: true }),
  ).toHaveValue("false");
  await expect(page.getByLabel("Event 1 delay", { exact: true })).toHaveValue(
    "33",
  );
  await expect(page.getByLabel("Event 2 delay", { exact: true })).toHaveValue(
    "33",
  );
});
