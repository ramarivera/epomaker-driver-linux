import { test, expect } from "@playwright/test";
const button = (page, name) => page.getByRole("button", { name, exact: true });
async function openPaint(page, request) {
  await request.post("/api/disconnect", {
    headers: { "X-Epomaker-Token": "ui-test-token" },
    data: {},
  });
  await page.goto("/#token=ui-test-token");
  await expect(button(page, "Refresh devices")).toBeEnabled();
  await button(page, "Display").click();
  await button(page, "New blank draft").click();
  await expect(button(page, "Paint this frame")).toBeEnabled();
  await button(page, "Paint this frame").click();
  await expect(button(page, "Apply painting to draft")).toBeEnabled();
  return page.getByRole("img", { name: "Frame painting canvas", exact: true });
}
const pixel = (canvas, x, y) =>
  canvas.evaluate(
    (el, [x, y]) =>
      Array.from(el.getContext("2d").getImageData(x, y, 1, 1).data),
    [x, y],
  );
async function clickPixel(page, canvas, x, y) {
  const box = await canvas.boundingBox();
  await page.mouse.click(
    box.x + ((x + 0.5) * box.width) / 428,
    box.y + ((y + 0.5) * box.height) / 142,
  );
}
test("painting is pixel aligned, reversible, zoomable and applied only to the draft", async ({
  page,
  request,
}) => {
  const writes = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/write")) writes.push(r);
  });
  const canvas = await openPaint(page, request);
  const original = await page
    .locator(".display-preview img")
    .getAttribute("src");
  await page.getByLabel("Paint color", { exact: true }).fill("#ff0000");
  await page.getByLabel("Brush width", { exact: true }).selectOption("5");
  await clickPixel(page, canvas, 10, 10);
  expect(await pixel(canvas, 8, 8)).toEqual([255, 0, 0, 255]);
  expect(await pixel(canvas, 12, 12)).toEqual([255, 0, 0, 255]);
  expect(await pixel(canvas, 7, 10)).toEqual([0, 0, 0, 255]);
  await button(page, "Undo stroke").click();
  expect(await pixel(canvas, 10, 10)).toEqual([0, 0, 0, 255]);
  await button(page, "Redo stroke").click();
  expect(await pixel(canvas, 10, 10)).toEqual([255, 0, 0, 255]);
  await page.getByLabel("Paint tool", { exact: true }).selectOption("eraser");
  await page.getByLabel("Brush width", { exact: true }).selectOption("1");
  await clickPixel(page, canvas, 10, 10);
  expect(await pixel(canvas, 10, 10)).toEqual([0, 0, 0, 255]);
  expect(await pixel(canvas, 9, 10)).toEqual([255, 0, 0, 255]);
  await page.getByLabel("Canvas zoom", { exact: true }).selectOption("2");
  await page.getByLabel("Paint tool", { exact: true }).selectOption("brush");
  await clickPixel(page, canvas, 20, 20);
  expect(await pixel(canvas, 20, 20)).toEqual([255, 0, 0, 255]);
  await canvas.focus();
  const box = await canvas.boundingBox();
  await page.keyboard.down("Space");
  await page.mouse.move(box.x + 250, box.y + 100);
  await page.mouse.down();
  await page.mouse.move(box.x + 100, box.y + 50);
  await page.mouse.up();
  await page.keyboard.up("Space");
  expect(
    await page
      .locator(".display-paint-viewport")
      .evaluate((el) => el.scrollLeft),
  ).toBeGreaterThan(0);
  await button(page, "Reset canvas view").click();
  await expect(page.getByLabel("Canvas zoom", { exact: true })).toHaveValue(
    "1",
  );
  await button(page, "Apply painting to draft").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".display-preview img")).not.toHaveAttribute(
    "src",
    original,
  );
  await button(page, "Undo frame edit").click();
  await expect(page.locator(".display-preview img")).toHaveAttribute(
    "src",
    original,
  );
  expect(writes).toHaveLength(0);
});
test("cancel discards painting and failed apply retains it for retry", async ({
  page,
  request,
}) => {
  let canvas = await openPaint(page, request);
  const original = await page
    .locator(".display-preview img")
    .getAttribute("src");
  await clickPixel(page, canvas, 12, 12);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".display-preview img")).toHaveAttribute(
    "src",
    original,
  );
  await button(page, "Paint this frame").click();
  await expect(button(page, "Apply painting to draft")).toBeEnabled();
  canvas = page.getByRole("img", {
    name: "Frame painting canvas",
    exact: true,
  });
  expect(await pixel(canvas, 12, 12)).toEqual([0, 0, 0, 255]);
  await clickPixel(page, canvas, 12, 12);
  await page.route("**/api/display_edit", (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "Replacement rejected" }),
    }),
  );
  await button(page, "Apply painting to draft").click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "It is retained here",
  );
  expect(await pixel(canvas, 12, 12)).toEqual([255, 255, 255, 255]);
  await expect(page.locator(".display-preview img")).toHaveAttribute(
    "src",
    original,
  );
  await page.unroute("**/api/display_edit");
  await button(page, "Apply painting to draft").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("stroke history is bounded and pointer cancellation restores the previous pixels", async ({
  page,
  request,
}) => {
  const canvas = await openPaint(page, request);
  for (let x = 1; x <= 11; x++) await clickPixel(page, canvas, x, 10);
  for (let count = 0; count < 10; count++)
    await button(page, "Undo stroke").click();
  await expect(button(page, "Undo stroke")).toBeDisabled();
  expect(await pixel(canvas, 1, 10)).toEqual([255, 255, 255, 255]);
  expect(await pixel(canvas, 2, 10)).toEqual([0, 0, 0, 255]);
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + 61, box.y + 61);
  await page.mouse.down();
  await canvas.dispatchEvent("pointercancel");
  await page.mouse.up();
  expect(await pixel(canvas, 30, 30)).toEqual([0, 0, 0, 255]);
  await expect(button(page, "Undo stroke")).toBeDisabled();
});
