import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

test("legacy Glyph backup reports its skipped debounce setting", async ({
  page,
}) => {
  await page.goto("/#token=ui-test-token");
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply to keyboard", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Backups", exact: true }).click();
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download backup", exact: true })
    .click();
  const downloaded = await pending;
  const backup = JSON.parse(await readFile(await downloaded.path(), "utf8"));
  expect(backup.debounce).toBeNull();
  backup.debounce = 9;
  await page.getByLabel("Backup file", { exact: true }).setInputFiles({
    name: "legacy-glyph.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(backup)),
  });
  await page
    .getByRole("button", { name: "Restore backup", exact: true })
    .click();
  await expect(
    page.getByText("Restoration verified.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("note", { name: "Restore limitations", exact: true }),
  ).toContainText("legacy Glyph debounce value is not restored");
});
