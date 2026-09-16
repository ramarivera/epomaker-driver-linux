import { test, expect } from "@playwright/test";
const content =
  "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAIAAAALAAAAAACAAIAAAgGAAEIBBAQADs=";
const headers = { "X-Epomaker-Token": "ui-test-token" };
const button = (page, name) => page.getByRole("button", { name, exact: true });
async function prepare(page, request) {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await expect(button(page, "Refresh devices")).toBeEnabled();
  await button(page, "Display").click();
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "red.png",
    mimeType: "image/png",
    buffer: Buffer.from(content, "base64"),
  });
  await button(page, "Prepare preview").click();
  await expect(button(page, "Insert black frame")).toBeEnabled();
}
test("edited frames preserve duplicates through undo, reprepare and library reload without writes", async ({
  page,
  request,
}) => {
  const writes = [];
  page.on("request", (r) => {
    if (r.url().endsWith("/api/write")) writes.push(r);
  });
  await prepare(page, request);
  const image = page.locator(".display-preview img");
  const red = await image.getAttribute("src");
  await button(page, "Insert black frame").click();
  await expect(page.getByLabel("Preview frame")).toHaveValue("1");
  await expect(page.getByLabel("Upload as")).toHaveValue("animation");
  await expect(page.getByLabel("Frame delay (ms, optional)")).toHaveValue("80");
  const black = await image.getAttribute("src");
  expect(black).not.toBe(red);
  await button(page, "Copy previous into this frame").click();
  await expect(image).toHaveAttribute("src", red);
  await button(page, "Undo frame edit").click();
  await expect(image).toHaveAttribute("src", black);
  await button(page, "Redo frame edit").click();
  await expect(image).toHaveAttribute("src", red);
  await page.getByLabel("Frame delay (ms, optional)").fill("0");
  await button(page, "Prepare preview").click();
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    2,
  );
  await page.getByLabel("Preview frame").selectOption("1");
  await expect(image).toHaveAttribute("src", red);
  await expect(button(page, "Undo frame edit")).toBeDisabled();
  await page
    .getByLabel("Asset name", { exact: true })
    .fill("Edited duplicate frames");
  await button(page, "Save prepared asset").click();
  await expect(button(page, "Load asset into editor")).toBeEnabled();
  await button(page, "Clear all frames").click();
  await expect(page.getByLabel("Upload as")).toHaveValue("screen");
  await expect(image).toHaveAttribute("src", black);
  await expect(button(page, "Delete this frame")).toBeDisabled();
  await button(page, "Load asset into editor").click();
  await expect(page.getByLabel("Preview frame").locator("option")).toHaveCount(
    2,
  );
  await expect(page.getByLabel("Frame delay (ms, optional)")).toHaveValue("0");
  await page.getByLabel("Preview frame").selectOption("1");
  await expect(image).toHaveAttribute("src", red);
  await expect(button(page, "Undo frame edit")).toBeDisabled();
  await button(page, "Delete asset").click();
  expect(writes).toHaveLength(0);
});
test("pending and failed frame edits preserve the draft and lock its controls", async ({
  page,
  request,
}) => {
  await prepare(page, request);
  const original = await page
    .locator(".display-preview img")
    .getAttribute("src");
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/display_edit", async (route) => {
    await gate;
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: "Frame edit rejected" }),
    });
  });
  const pending = page.waitForRequest("**/api/display_edit");
  await button(page, "Clear this frame").click();
  await pending;
  for (const name of [
    "Insert black frame",
    "Clear this frame",
    "Prepare preview",
    "Save prepared asset",
  ])
    await expect(button(page, name)).toBeDisabled();
  await expect(page.getByLabel("Image file", { exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole("alert")).toContainText("Frame edit rejected");
  await expect(page.locator(".display-preview img")).toHaveAttribute(
    "src",
    original,
  );
  await expect(button(page, "Undo frame edit")).toBeDisabled();
  await expect(button(page, "Clear this frame")).toBeEnabled();
});
