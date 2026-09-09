import { test, expect } from "@playwright/test";

async function connectToGlyph(page) {
  await page.goto("/#token=ui-test-token");
  await page.getByLabel("Device", { exact: true }).selectOption({
    label: "Glyph simulator · bluetooth",
  });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Macros", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Macros", exact: true }),
  ).toBeVisible();
}

test("records physical modifier and key, previews, validates, saves and reads back", async ({
  page,
}) => {
  await connectToGlyph(page);
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  const pad = page.getByRole("textbox", {
    name: "Recording area",
    exact: true,
  });
  await expect(pad).toBeFocused();
  await page.keyboard.down("Shift");
  await page.keyboard.press("a");
  await page.keyboard.up("Shift");
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(page.getByText(/Recorded 4 actions/)).toBeVisible();
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await expect(page.getByText(/Preview: 4 actions/)).toBeVisible();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
  await expect(
    page.getByLabel("Event 2 key usage", { exact: true }),
  ).toHaveValue("4");
  await page.getByRole("button", { name: "Save macro", exact: true }).click();
  await expect(
    page.getByText("Macro readback verified.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New macro", exact: true }).click();
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(
    page.getByLabel("Event 2 key usage", { exact: true }),
  ).toHaveValue("4");
});

test("cancel preserves the editor and blur releases held keys", async ({
  page,
}) => {
  await connectToGlyph(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  const pad = page.getByRole("textbox", {
    name: "Recording area",
    exact: true,
  });
  await expect(pad).toBeFocused();
  await page.keyboard.down("Control");
  await pad.evaluate((node) => node.blur());
  await expect(page.getByText(/Recorded \d+ actions/)).toBeVisible();
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await expect(page.getByText(/Release Control Left/)).toBeVisible();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page
    .getByRole("button", { name: "Discard recording", exact: true })
    .click();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByRole("button", { name: "Start recording", exact: true }),
  ).toBeVisible();
});

async function startCapture(page) {
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Recording area", exact: true }),
  ).toBeFocused();
}
async function acceptCapture(page) {
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
}

test("Tab records, Escape stops, auto-repeat is ignored and trailing delay is 50 ms", async ({
  page,
}) => {
  await connectToGlyph(page);
  await startCapture(page);
  await page.keyboard.down("a");
  await page.keyboard.down("a");
  await page.keyboard.up("a");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Escape");
  await expect(page.getByText(/Recorded 4 actions/)).toBeVisible();
  await acceptCapture(page);
  await expect(
    page.getByLabel("Event 3 key usage", { exact: true }),
  ).toHaveValue("43");
  await expect(page.getByLabel("Event 4 delay", { exact: true })).toHaveValue(
    "50",
  );
});

test("Cancel while recording preserves existing editor and clears the draft", async ({
  page,
}) => {
  await connectToGlyph(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await startCapture(page);
  await page.keyboard.press("b");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toHaveCount(0);
});

test("fixed delay validates bounds and includes generated modifier releases", async ({
  page,
}) => {
  await connectToGlyph(page);
  await page
    .getByLabel("Recording delay mode", { exact: true })
    .selectOption("fixed");
  await page.getByLabel("Fixed recording delay", { exact: true }).fill("0");
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "integer from 1 through 65535",
  );
  await page.getByLabel("Fixed recording delay", { exact: true }).fill("200");
  await startCapture(page);
  await page.keyboard.down("Control");
  await page.keyboard.press("b");
  await page.keyboard.press("Escape");
  await page.keyboard.up("Control");
  await expect(page.getByRole("note")).toContainText("Added 1 release action");
  await acceptCapture(page);
  for (let i = 1; i <= 4; i++)
    await expect(
      page.getByLabel(`Event ${i} delay`, { exact: true }),
    ).toHaveValue("200");
  await expect(
    page.getByLabel("Event 4 key usage", { exact: true }),
  ).toHaveValue("224");
  await expect(
    page.getByLabel("Event 4 direction", { exact: true }),
  ).toHaveValue("false");
});

test("capacity overflow blocks use and preserves the editor", async ({
  page,
}) => {
  await connectToGlyph(page);
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await startCapture(page);
  for (let i = 0; i < 70; i++) await page.keyboard.press("a");
  await expect(page.getByRole("alert")).toContainText("capacity");
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
});

test("unknown physical codes cannot silently become an accepted macro", async ({
  page,
}) => {
  await connectToGlyph(page);
  await startCapture(page);
  await page.keyboard.press("a");
  await page
    .getByRole("textbox", { name: "Recording area", exact: true })
    .dispatchEvent("keydown", { code: "Unidentified", key: "Unidentified" });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alert")).toContainText(
    "Unsupported physical key code",
  );
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toBeDisabled();
});

test("unrepresentable measured holds are rejected while fixed holds ignore elapsed time", async ({
  page,
}) => {
  await page.clock.install();
  await connectToGlyph(page);
  await startCapture(page);
  await page.keyboard.down("a");
  await page.clock.fastForward(70000);
  await page.keyboard.press("Escape");
  await page.keyboard.up("a");
  await expect(page.getByRole("alert")).toContainText("65535");
  await expect(
    page.getByRole("button", { name: "Use recording", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Recording delay mode", { exact: true })
    .selectOption("fixed");
  await page.getByLabel("Fixed recording delay", { exact: true }).fill("150");
  await startCapture(page);
  await page.keyboard.down("a");
  await page.clock.fastForward(70000);
  await page.keyboard.press("Escape");
  await page.keyboard.up("a");
  await acceptCapture(page);
  await expect(page.getByLabel("Event 1 delay", { exact: true })).toHaveValue(
    "150",
  );
  await expect(page.getByLabel("Event 2 delay", { exact: true })).toHaveValue(
    "150",
  );
});

test("pending recording validation locks editor replacement and performs no device writes", async ({
  page,
}) => {
  await connectToGlyph(page);
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await startCapture(page);
  await page.keyboard.press("a");
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Use recording", exact: true })
    .click();
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/validate_macro", async (route) => {
    await pending;
    await route.continue();
  });
  await page
    .getByRole("button", { name: "Replace editor with recording", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "New macro", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Load macro", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Import JSON", { exact: true })).toBeDisabled();
  release();
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
  await expect(
    page.getByRole("button", { name: "New macro", exact: true }),
  ).toBeEnabled();
  expect(writes).toHaveLength(0);
});
