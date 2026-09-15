import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("layout crop and inverse rotation sample real canvas pixels without stale output", async ({
  page,
}) => {
  await page.route("**/layout-test-module.js", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: readFileSync(
        new URL("../src/rhythm-layout.js", import.meta.url),
        "utf8",
      ),
    }),
  );
  await page.goto("/#token=ui-test-token");
  const pixels = await page.evaluate(async () => {
    const { sampleRhythm, RHYTHM_CANVAS } =
      await import("/layout-test-module.js");
    const source = document.createElement("canvas");
    source.width = RHYTHM_CANVAS.width;
    source.height = RHYTHM_CANVAS.height;
    const ctx = source.getContext("2d");
    ctx.fillStyle = "#0000ff";
    ctx.fillRect(0, 0, source.width, source.height);
    ctx.fillStyle = "#ff0000";
    ctx.fillRect(0, 0, 45, source.height);
    const output = document.createElement("canvas");
    output.width = 21;
    output.height = 6;
    const out = output.getContext("2d");
    const scratch = document.createElement("canvas");
    const layout = { x: 0, y: 24, width: 90, height: 60, rotation: 0 };
    const sample = (x, y) => Array.from(out.getImageData(x, y, 1, 1).data);
    sampleRhythm(out, source, layout, scratch);
    const direct = [sample(2, 3), sample(18, 3)];
    sampleRhythm(out, source, { ...layout, rotation: 180 }, scratch);
    const reversed = [sample(2, 3), sample(18, 3)];
    ctx.clearRect(0, 0, source.width, source.height);
    sampleRhythm(out, source, { ...layout, rotation: 180 }, scratch);
    const cleared = Array.from(out.getImageData(0, 0, 21, 6).data);
    return { direct, reversed, cleared };
  });
  expect(pixels.direct).toEqual([
    [255, 0, 0, 255],
    [0, 0, 255, 255],
  ]);
  expect(pixels.reversed).toEqual([
    [0, 0, 255, 255],
    [255, 0, 0, 255],
  ]);
  // Transparent or black are acceptable: frameColors premultiplies alpha.
  for (let i = 0; i < pixels.cleared.length; i += 4) {
    expect(pixels.cleared[i] * pixels.cleared[i + 3]).toBe(0);
    expect(pixels.cleared[i + 1] * pixels.cleared[i + 3]).toBe(0);
    expect(pixels.cleared[i + 2] * pixels.cleared[i + 3]).toBe(0);
  }
});
