import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

const colors = Array.from({ length: 126 }, (_, index) =>
  index.toString(16).padStart(6, "0"),
);
const patternFile = {
  name: "keyboard-pattern.json",
  mimeType: "application/json",
  buffer: Buffer.from(
    JSON.stringify({
      schema: "epomaker-glyph-pattern",
      version: 1,
      model_id: 3059,
      colors,
    }),
  ),
};
const slotMappingPromise = readFile(
  new URL("../../docs/releases/glyph-pattern-key-slots.json", import.meta.url),
  "utf8",
).then((contents) => {
  const mapping = JSON.parse(contents);
  return Object.fromEntries(
    mapping.records.map(({ key, slot }) => [key, slot]),
  );
});

test("pattern keyboard paints mapped physical keys and preserves hidden slots", async ({
  page,
}) => {
  const slotMapping = await slotMappingPromise;
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await page
    .getByLabel("Import pattern JSON", { exact: true })
    .setInputFiles(patternFile);
  const keys = page.getByRole("button", { name: /^Paint key / });
  await expect(keys).toHaveCount(86);
  for (const name of [
    "A",
    "Shift Left",
    "Shift Right",
    "Space",
    "AudioVolumeDown",
    "MediaPlayPause",
    "AudioVolumeUp",
  ]) {
    await expect(
      page.getByRole("button", { name: `Paint key ${name}`, exact: true }),
    ).toBeEnabled();
  }
  await page.getByLabel("Paint color", { exact: true }).fill("#abcdef");
  const targets = [
    ["A", "KeyA"],
    ["Shift Left", "ShiftLeft"],
    ["Shift Right", "ShiftRight"],
    ["Space", "Space"],
    ["AudioVolumeDown", "AudioVolumeDown"],
    ["MediaPlayPause", "MediaPlayPause"],
    ["AudioVolumeUp", "AudioVolumeUp"],
  ];
  const paintedSlots = {};
  for (const [label, canonicalName] of targets) {
    const key = page.getByRole("button", {
      name: `Paint key ${label}`,
      exact: true,
    });
    const title = await key.getAttribute("title");
    const uiSlot = Number(title.match(/RGB slot (\d+)/)[1]);
    expect(uiSlot).toBe(slotMapping[canonicalName]);
    paintedSlots[slotMapping[canonicalName]] = "abcdef";
    await key.click();
  }
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export pattern JSON", exact: true })
    .click();
  const exported = JSON.parse(
    await readFile(await (await downloadPromise).path(), "utf8"),
  );
  for (const [slot, original] of colors.entries()) {
    expect(exported.colors[slot]).toBe(paintedSlots[slot] || original);
  }
});

test("pattern keyboard remains readable on a narrow viewport", async ({
  page,
}) => {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await page.getByRole("button", { name: "New pattern", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const keyboard = page.locator(".pattern-keyboard");
  await expect(keyboard).toBeVisible();
  expect((await keyboard.boundingBox()).width).toBeGreaterThan(390);
  const overflow = await page
    .locator(".pattern-keyboard-scroll")
    .evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
  expect(overflow.scrollWidth).toBeGreaterThan(overflow.clientWidth);
  const documentWidth = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(documentWidth.scrollWidth).toBeLessThanOrEqual(
    documentWidth.clientWidth,
  );
  await expect(
    page.getByRole("button", { name: "Paint key A", exact: true }),
  ).toHaveAttribute("title", /RGB slot/);
});
