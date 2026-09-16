import { test, expect } from "@playwright/test";
const gif = {
  name: "two-colors.gif",
  mimeType: "image/gif",
  buffer: Buffer.from(
    "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAIAAAALAAAAAACAAIAAAgGAAEIBBAQACH5BAEIAAEALAAAAAACAAIAgQAA/wAAAAAAAAAAAAgGAAEIBBAQADs=",
    "base64",
  ),
};
const headers = { "X-Epomaker-Token": "ui-test-token" };
async function prepare(page, request, zero = false) {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await page.getByLabel("Image file", { exact: true }).setInputFiles(gif);
  if (zero) await page.getByLabel("Frame delay (ms, optional)").fill("0");
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(page.getByLabel("Preview frame")).toHaveValue("0");
}
test("converted animation frames can be inspected and played without device writes", async ({
  page,
  request,
}) => {
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request.url());
  });
  await prepare(page, request);
  const image = page.locator(".display-preview img");
  const first = await image.getAttribute("src");
  await page.getByRole("button", { name: "Next frame", exact: true }).click();
  await expect(page.getByLabel("Preview frame")).toHaveValue("1");
  await expect(image).not.toHaveAttribute("src", first);
  await expect(image).toHaveAttribute(
    "alt",
    "Prepared display pixels, frame 2",
  );
  await expect(
    page.getByRole("button", { name: "Next frame", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Previous frame", exact: true })
    .click();
  await expect(image).toHaveAttribute("src", first);
  await page.clock.install();
  await page.clock.pauseAt(new Date());
  await page.getByRole("button", { name: "Play preview", exact: true }).click();
  await page.clock.runFor(80);
  await expect(page.getByLabel("Preview frame")).toHaveValue("1");
  await page
    .getByRole("button", { name: "Pause preview", exact: true })
    .click();
  await page.clock.runFor(240);
  await expect(page.getByLabel("Preview frame")).toHaveValue("1");
  await page.getByLabel("Preview frame").selectOption("0");
  await page.getByRole("button", { name: "Play preview", exact: true }).click();
  await page.getByLabel("Frame delay (ms, optional)").fill("120");
  await page.clock.runFor(240);
  await expect(page.getByLabel("Preview frame")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Upload to display", exact: true }),
  ).toBeDisabled();
  expect(writes).toEqual([]);
});
test("zero-delay animation retains manual inspection without guessed playback timing", async ({
  page,
  request,
}) => {
  await prepare(page, request, true);
  await expect(
    page.getByRole("button", { name: "Play preview", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Zero frame delay has no verified playback timing/),
  ).toBeVisible();
  await page.getByLabel("Preview frame").selectOption("1");
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, frame 2",
      exact: true,
    }),
  ).toBeVisible();
});
