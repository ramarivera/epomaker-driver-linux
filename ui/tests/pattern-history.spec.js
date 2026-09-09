import { test, expect } from "@playwright/test";

const colors = (first = "000000") => [first, ...Array(125).fill("000000")];
const file = (value) => ({
  name: "pattern.json",
  mimeType: "application/json",
  buffer: Buffer.from(
    JSON.stringify({
      schema: "epomaker-glyph-pattern",
      version: 1,
      model_id: 3059,
      colors: value,
    }),
  ),
});

async function openLighting(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices" }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", { name: "Disconnect" });
  if (await disconnect.isVisible()) await disconnect.click();
  await page.getByRole("button", { name: "Lighting" }).click();
}

test("paint, fill, and new pattern undo and redo draft edits", async ({
  page,
}) => {
  await openLighting(page);
  await page.getByRole("button", { name: "New pattern" }).click();
  await page.getByLabel("Paint color").fill("#abcdef");
  await page.getByRole("button", { name: "Color slot 0" }).click();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Color slot 0" })).toHaveCSS(
    "background-color",
    "rgb(0, 0, 0)",
  );
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(page.getByRole("button", { name: "Color slot 0" })).toHaveCSS(
    "background-color",
    "rgb(171, 205, 239)",
  );
  await page.getByRole("button", { name: "Fill all" }).click();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(
    page.getByRole("button", { name: "Color slot 1", exact: true }),
  ).toHaveCSS("background-color", "rgb(0, 0, 0)");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(
    page.getByRole("button", { name: "Save pattern" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(
    page.getByRole("button", { name: "Save pattern" }),
  ).toBeDisabled();
});

test("successful import is undoable, failed import preserves history, and new edit clears redo", async ({
  page,
}) => {
  await openLighting(page);
  await page
    .getByLabel("Import pattern JSON")
    .setInputFiles(file(colors("123456")));
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Color slot 0" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Redo" }).click();
  await page.getByLabel("Import pattern JSON").setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        schema: "wrong",
        version: 1,
        model_id: 3059,
        colors: colors(),
      }),
    ),
  });
  await expect(page.getByRole("alert")).toContainText(
    "Unsupported pattern schema",
  );
  await expect(page.getByRole("button", { name: "Color slot 0" })).toHaveCSS(
    "background-color",
    "rgb(18, 52, 86)",
  );
  await page.getByRole("button", { name: "Color slot 0" }).click();
  await expect(page.getByRole("button", { name: "Redo" })).toBeDisabled();
});

test("changing banks resets history and undo never writes to the device", async ({
  page,
}) => {
  await openLighting(page);
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page.getByRole("button", { name: "New pattern" }).click();
  await page.getByLabel("Pattern", { exact: true }).selectOption("1");
  await page.getByLabel("Pattern", { exact: true }).selectOption("0");
  await expect(page.getByRole("button", { name: "Undo" })).toBeDisabled();
  expect(writes).toHaveLength(0);
});
