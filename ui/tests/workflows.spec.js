import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
});
async function connect(page) {
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply to keyboard", exact: true }),
  ).toBeEnabled();
}
async function nav(page, name) {
  await page.getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
}

test("offline preview, profile-aware key assignment, reconnect and responsive layout", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await expect(
    page.getByRole("button", { name: "Apply to keyboard", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Key B", exact: true }).click();
  await expect(page.getByLabel("Key", { exact: true })).toHaveValue("5");
  await connect(page);
  await page.getByLabel("Profile", { exact: true }).selectOption("1");
  await expect(
    page.getByRole("button", { name: "Apply to keyboard" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Key A", exact: true }).click();
  await page.getByLabel("Key", { exact: true }).selectOption({ label: "B" });
  await page.getByLabel("Ctrl", { exact: true }).check();
  await page.getByRole("button", { name: "Apply to keyboard" }).click();
  await expect(
    page.getByText("Assignment verified.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Key S", exact: true }).click();
  await page.getByRole("button", { name: "Key A", exact: true }).click();
  await expect(page.getByLabel("Key", { exact: true })).toHaveValue("5");
  await expect(page.getByLabel("Ctrl", { exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Fn Windows", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply to keyboard" }),
  ).toBeEnabled();
  await page.getByLabel("Action", { exact: true }).selectOption("Disabled");
  await page.getByRole("button", { name: "Apply to keyboard" }).click();
  await expect(
    page.getByText("Assignment verified.", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Current assignment", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("main and side lighting, custom color pattern, settings", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "Lighting");
  await page.getByLabel("Effect", { exact: true }).selectOption("solid");
  await page.getByLabel("Color", { exact: true }).fill("#123456");
  await page
    .getByRole("button", { name: "Apply lighting", exact: true })
    .click();
  await expect(
    page.getByText("Lighting read back from keyboard.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Side lighting", exact: true })
    .click();
  await page.getByLabel("Color", { exact: true }).fill("#fedcba");
  await page
    .getByRole("button", { name: "Apply lighting", exact: true })
    .click();
  await expect(
    page.getByText("Lighting read back from keyboard.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load pattern", exact: true }).click();
  await page.getByRole("button", { name: "Color slot 0", exact: true }).click();
  await page.getByRole("button", { name: "Save pattern", exact: true }).click();
  await expect(
    page.getByText("Pattern verified.", { exact: true }),
  ).toBeVisible();
  await nav(page, "Settings");
  await expect(page.getByLabel("Debounce (ms)", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Set debounce", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("System layer", { exact: true }).selectOption("mac");
  await page
    .getByRole("button", { name: "Apply OS options", exact: true })
    .click();
  await expect(
    page.getByText("OS options verified.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Apply timers", exact: true }).click();
  await expect(
    page.getByText("Sleep timers read back.", { exact: true }),
  ).toBeVisible();
});

test("macro edit and readback; invalid import preserves the editor", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "Macros");
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page.getByRole("button", { name: "Add event", exact: true }).click();
  await page
    .getByLabel("Event 2 direction", { exact: true })
    .selectOption("false");
  await page.getByRole("button", { name: "Save macro", exact: true }).click();
  await expect(
    page.getByText("Macro readback verified.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New macro", exact: true }).click();
  await page.getByRole("button", { name: "Load macro", exact: true }).click();
  await expect(
    page.getByLabel("Event 2 direction", { exact: true }),
  ).toHaveValue("false");
  await page.getByLabel("Import JSON", { exact: true }).setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"repeat":1,"events":[null]}'),
  });
  await expect(page.getByRole("alert")).toContainText(
    "each event must be an object",
  );
  await expect(
    page.getByLabel("Event 1 key usage", { exact: true }),
  ).toHaveValue("4");
});

test("display image upload, clock, backup download and verified restore", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "Display");
  await page.getByLabel("Still image bank", { exact: true }).selectOption("4");
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "pixel.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPioAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await page
    .getByRole("button", { name: "Upload to display", exact: true })
    .click();
  await expect(
    page.getByText("Image transfer finished. Check the keyboard display.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sync clock", exact: true }).click();
  await expect(page.getByText("Clock sent.", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Toggle display language", exact: true })
    .click();
  await expect(
    page.getByText("Language toggle sent. Check the keyboard display.", {
      exact: true,
    }),
  ).toBeVisible();
  await nav(page, "Backups");
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download backup", exact: true })
    .click();
  const download = await pending;
  await page
    .getByLabel("Backup file", { exact: true })
    .setInputFiles(await download.path());
  await page
    .getByRole("button", { name: "Restore backup", exact: true })
    .click();
  await expect(
    page.getByText("Restoration verified.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Recovery copy:/)).toContainText("recovery-");
});

test("Glyph factory reset saves recovery and requires reconnect", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "Backups");
  await page
    .getByLabel(
      "I understand that factory reset changes the keyboard configuration.",
      {
        exact: true,
      },
    )
    .check();
  await page
    .getByRole("button", { name: "Factory reset Glyph", exact: true })
    .click();
  await expect(
    page.getByText(
      "Factory reset sent. Reconnect to continue; defaults were not verified.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText(/Reset command sent\. Reconnect required\./),
  ).toBeVisible();
  await expect(
    page.getByText("Offline preview", { exact: true }),
  ).toBeVisible();
});

test("failed reset clears confirmation and stale connection", async ({
  page,
}) => {
  await connect(page);
  await nav(page, "Backups");
  await page.route("**/api/write", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({
        error:
          "reset outcome is unknown; recovery snapshot is saved at /test/recovery.json",
      }),
    });
  });
  const confirmation = page.getByRole("checkbox", {
    name: "I understand that factory reset changes the keyboard configuration.",
    exact: true,
  });
  await confirmation.check();
  await page
    .getByRole("button", { name: "Factory reset Glyph", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("/test/recovery.json");
  await expect(
    page.getByText("Offline preview", { exact: true }),
  ).toBeVisible();
  await expect(confirmation).not.toBeChecked();
  await expect(
    page.getByText(/Reset command sent\. Reconnect required\./),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Download backup", exact: true }),
  ).toBeDisabled();
});
