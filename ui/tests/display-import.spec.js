import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
const gif = Buffer.from(
  "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAIAAAALAAAAAACAAIAAAgGAAEIBBAQACH5BAEIAAEALAAAAAACAAIAgQAA/wAAAAAAAAAAAAgGAAEIBBAQADs=",
  "base64",
);
for (
  let pos = gif.indexOf(Buffer.from([0x21, 0xf9, 4]));
  pos >= 0;
  pos = gif.indexOf(Buffer.from([0x21, 0xf9, 4]), pos + 1)
)
  gif.writeUInt16LE(0, pos + 4);
const animation = {
  name: "replacement.gif",
  mimeType: "image/gif",
  buffer: gif,
};
const still = {
  name: "still.png",
  mimeType: "image/png",
  buffer: Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPioAAAAASUVORK5CYII=",
    "base64",
  ),
};
const button = (page, name) => page.getByRole("button", { name, exact: true });
async function prepare(page, request) {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await expect(button(page, "Refresh devices")).toBeEnabled();
  await button(page, "Display").click();
  await page.getByLabel("Image file", { exact: true }).setInputFiles(animation);
  await button(page, "Prepare preview").click();
  await expect(page.getByLabel("Preview frame")).toHaveValue("0");
  await page.getByLabel("Preview frame").selectOption("1");
}
async function importFile(page, file) {
  await page.getByLabel("Import image with placement").setInputFiles(file);
  await expect(
    page.getByRole("dialog", { name: "Prepare display image" }),
  ).toBeVisible();
  await expect(button(page, "Apply image")).toBeEnabled();
}
test("still placement preserves other frames and cancel preserves the entire draft", async ({
  page,
  request,
}) => {
  const writes = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/write")) writes.push(r);
  });
  await prepare(page, request);
  const image = page.locator(".display-preview img");
  const before = await image.getAttribute("src");
  await importFile(page, still);
  await expect(
    page.getByText("This still image replaces the current frame.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByLabel("Scale", { exact: true }).selectOption("40");
  expect(Number(await page.getByLabel("Position X").inputValue())).toBeCloseTo(
    185.6,
  );
  const view = page.locator(".display-import-viewport");
  const box = await view.boundingBox();
  await page.mouse.move(box.x + 100, box.y + 50);
  await page.mouse.down();
  await page.mouse.move(box.x + 120, box.y + 60);
  await page.mouse.up();
  expect(Number(await page.getByLabel("Position X").inputValue())).toBeCloseTo(
    185.6 + (20 * 428) / box.width,
  );
  await page.mouse.wheel(0, -100);
  await expect(page.getByLabel("Scale", { exact: true })).toHaveValue("60");
  expect(Number(await page.getByLabel("Position X").inputValue())).toBeCloseTo(
    171.4,
  );
  await page.getByLabel("Position X").fill("");
  await expect(button(page, "Apply image")).toBeDisabled();
  await button(page, "Cancel").click();
  await expect(image).toHaveAttribute("src", before);
  await importFile(page, still);
  await page.getByLabel("Scale", { exact: true }).selectOption("40");
  await page.getByLabel("Position X").fill("0");
  await page.getByLabel("Position Y").fill("0");
  await button(page, "Apply image").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Preview frame")).toHaveValue("1");
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    2,
  );
  await expect(page.getByLabel("Frame delay (ms, optional)")).toHaveValue("0");
  await expect(image).not.toHaveAttribute("src", before);
  await button(page, "Undo frame edit").click();
  await expect(image).toHaveAttribute("src", before);
  expect(writes).toHaveLength(0);
});
test("GIF import replaces the list, applies zero-delay fallback and preserves undo source identity", async ({
  page,
  request,
}) => {
  await prepare(page, request);
  await button(page, "Insert black frame").click();
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    3,
  );
  await importFile(page, { ...animation, name: "new-animation.gif" });
  await button(page, "Apply image").click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    2,
  );
  await expect(page.getByLabel("Preview frame")).toHaveValue("0");
  await expect(page.getByLabel("Frame delay (ms, optional)")).toHaveValue("60");
  await expect(
    page.getByText("Source: new-animation.gif", { exact: true }),
  ).toBeVisible();
  await button(page, "Undo frame edit").click();
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    3,
  );
  await expect(
    page.getByText("Source: replacement.gif", { exact: true }),
  ).toBeVisible();
});
test("rejected import keeps the dialog and does not alter the prepared draft", async ({
  page,
  request,
}) => {
  await prepare(page, request);
  const before = await page.locator(".display-preview img").getAttribute("src");
  await importFile(page, still);
  await page.route("**/api/display_import_transform", (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "Invalid placement" }),
    }),
  );
  await button(page, "Apply image").click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await expect(page.locator(".display-preview img")).toHaveAttribute(
    "src",
    before,
  );
  await expect(button(page, "Apply image")).toBeEnabled();
});
