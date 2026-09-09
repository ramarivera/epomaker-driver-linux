import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const colors = (first = "000000") => [first, ...Array(125).fill("000000")];
const fullColors = Array.from({ length: 126 }, (_, i) =>
  i.toString(16).padStart(6, "0"),
);
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
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Lighting", exact: true }),
  ).toBeVisible();
}

test("offline new/import/export preserves destination bank and strict format", async ({
  page,
}) => {
  await openLighting(page);
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page.getByLabel("Pattern", { exact: true }).selectOption("3");
  await page.getByRole("button", { name: "New pattern", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Save pattern", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: /Color slot/ })).toHaveCount(
    126,
  );
  await page
    .getByLabel("Import pattern JSON", { exact: true })
    .setInputFiles(file(colors("abcdef")));
  await expect(page.getByLabel("Pattern", { exact: true })).toHaveValue("3");
  await expect(
    page.getByRole("button", { name: "Color slot 0", exact: true }),
  ).toHaveCSS("background-color", "rgb(171, 205, 239)");
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export pattern JSON", exact: true })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("glyph-pattern-4.json");
  const exported = JSON.parse(await readFile(await download.path(), "utf8"));
  expect(exported).toEqual({
    schema: "epomaker-glyph-pattern",
    version: 1,
    model_id: 3059,
    colors: colors("abcdef"),
  });
  await page.getByRole("button", { name: "Fill all", exact: true }).click();
  expect(writes).toHaveLength(0);
});

test("invalid pattern imports preserve the existing draft", async ({
  page,
}) => {
  await openLighting(page);
  await page
    .getByLabel("Import pattern JSON", { exact: true })
    .setInputFiles(file(colors("123456")));
  await expect(
    page.getByRole("button", { name: "Color slot 0", exact: true }),
  ).toHaveCSS("background-color", "rgb(18, 52, 86)");
  await page.getByLabel("Import pattern JSON", { exact: true }).setInputFiles({
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
  await expect(
    page.getByRole("button", { name: "Color slot 0", exact: true }),
  ).toHaveCSS("background-color", "rgb(18, 52, 86)");
  for (const [field, value, message] of [
    ["version", 2, "Unsupported pattern version"],
    ["model_id", 1, "unsupported model"],
    ["colors", ["000000"], "exactly 126 colors"],
  ]) {
    const invalid = {
      schema: "epomaker-glyph-pattern",
      version: 1,
      model_id: 3059,
      colors: colors(),
    };
    invalid[field] = value;
    await page
      .getByLabel("Import pattern JSON", { exact: true })
      .setInputFiles({
        name: `${field}.json`,
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(invalid)),
      });
    await expect(page.getByRole("alert")).toContainText(message);
  }
  for (const [name, value, message] of [
    [
      "unknown.json",
      {
        schema: "epomaker-glyph-pattern",
        version: 1,
        model_id: 3059,
        colors: colors(),
        extra: true,
      },
      "unsupported fields",
    ],
    [
      "hex.json",
      {
        schema: "epomaker-glyph-pattern",
        version: 1,
        model_id: 3059,
        colors: colors("gggggg"),
      },
      "six-digit",
    ],
    ["null.json", null, "JSON object"],
  ]) {
    await page
      .getByLabel("Import pattern JSON", { exact: true })
      .setInputFiles({
        name,
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(value)),
      });
    await expect(page.getByRole("alert")).toContainText(message);
  }
  await page.getByLabel("Import pattern JSON", { exact: true }).setInputFiles({
    name: "large.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(65537, "x"),
  });
  await expect(page.getByRole("alert")).toContainText("64 KiB");
  await page.getByLabel("Import pattern JSON", { exact: true }).setInputFiles({
    name: "large.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        schema: "epomaker-glyph-pattern",
        version: 1,
        model_id: 3059,
        colors: colors("abcdef"),
      }),
    ),
  });
  await expect(
    page.getByRole("button", { name: "Color slot 0", exact: true }),
  ).toHaveCSS("background-color", "rgb(171, 205, 239)");
});

test("connected pattern load and save retain all 126 positions", async ({
  page,
}) => {
  await openLighting(page);
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page
    .getByLabel("Import pattern JSON", { exact: true })
    .setInputFiles(file(fullColors));
  await page.getByRole("button", { name: "Save pattern", exact: true }).click();
  await expect(
    page.getByText("Pattern verified.", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].postDataJSON()).toMatchObject({
    kind: "picture",
    index: 0,
    colors: fullColors.join(""),
  });
  await page.getByLabel("Pattern", { exact: true }).selectOption("1");
  await page.getByLabel("Pattern", { exact: true }).selectOption("0");
  await page.getByRole("button", { name: "Load pattern", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Color slot 125", exact: true }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export pattern JSON", exact: true })
    .click();
  const exported = JSON.parse(
    await readFile(await (await downloadPromise).path(), "utf8"),
  );
  expect(exported.colors).toEqual(fullColors);
});

test("pending pattern load locks bank selection and editing controls", async ({
  page,
}) => {
  let started;
  const startedPromise = new Promise((resolve) => {
    started = resolve;
  });
  let release;
  const responsePromise = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/read", async (route) => {
    const payload = route.request().postDataJSON();
    if (payload?.section !== "picture") return route.continue();
    started();
    await responsePromise;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ colors: "000000".repeat(126) }),
    });
  });
  await openLighting(page);
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph simulator · bluetooth" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Load pattern", exact: true }).click();
  await startedPromise;
  await expect(page.getByLabel("Pattern", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "New pattern", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Import pattern JSON", { exact: true }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByRole("button", { name: "Color slot 125", exact: true }),
  ).toBeVisible();
});
