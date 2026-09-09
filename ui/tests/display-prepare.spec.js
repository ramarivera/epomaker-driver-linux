import { test, expect } from "@playwright/test";
const png = {
  name: "pixel.png",
  mimeType: "image/png",
  buffer: Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPioAAAAASUVORK5CYII=",
    "base64",
  ),
};
async function openDisplay(page) {
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  const disconnect = page.getByRole("button", {
    name: "Disconnect",
    exact: true,
  });
  if (await disconnect.isVisible()) await disconnect.click();
  await page.getByRole("button", { name: "Display", exact: true }).click();
}
test("offline preparation previews converted pixels without device writes and invalidates changed input", async ({
  page,
}) => {
  await openDisplay(page);
  const writes = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/write")) writes.push(request);
  });
  await page.getByLabel("Image file", { exact: true }).setInputFiles(png);
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  const image = page.getByRole("img", {
    name: "Prepared display pixels, first frame",
    exact: true,
  });
  await expect(image).toBeVisible();
  await expect(
    page.getByText("1 frame · 121,552 pixel bytes", { exact: true }),
  ).toBeVisible();
  expect(
    await image.evaluate((el) => [el.naturalWidth, el.naturalHeight]),
  ).toEqual([428, 142]);
  await expect(
    page.getByRole("button", { name: "Upload to display", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Still image bank", { exact: true }).selectOption("4");
  await expect(image).toBeVisible();
  await page.getByLabel("Upload as", { exact: true }).selectOption("animation");
  await expect(image).toHaveCount(0);
  await page
    .getByLabel("Frame delay (ms, optional)", { exact: true })
    .fill("2.5");
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Frame delay must be an integer",
  );
  expect(writes).toHaveLength(0);
});
test("invalid image preparation reports failure and never enables upload", async ({
  page,
}) => {
  await openDisplay(page);
  await page
    .getByLabel("Image file", { exact: true })
    .setInputFiles({ ...png, buffer: Buffer.from("not an image") });
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, first frame",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Upload to display", exact: true }),
  ).toBeDisabled();
});
test("preparation locks its source, type, bank, and upload until complete", async ({
  page,
}) => {
  await openDisplay(page);
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/display_prepare", async (route) => {
    await gate;
    await route.continue();
  });
  await page.getByLabel("Image file", { exact: true }).setInputFiles(png);
  const pending = page.waitForRequest("**/api/display_prepare");
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await pending;
  for (const label of ["Image file", "Upload as", "Still image bank"])
    await expect(page.getByLabel(label, { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Upload to display", exact: true }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, first frame",
      exact: true,
    }),
  ).toBeVisible();
});

test("animation preparation reports averaged and overridden timing", async ({
  page,
}) => {
  await openDisplay(page);
  await page.getByLabel("Image file", { exact: true }).setInputFiles({
    name: "two-frames.gif",
    mimeType: "image/gif",
    buffer: Buffer.from(
      "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAEAAAALAAAAAACAAIAAAgGAAEIBBAQACH5BAEIAAEALAAAAAACAAIAgQAA/wAAAAAAAAAAAAgGAAEIBBAQADs=",
      "base64",
    ),
  });
  await expect(page.getByLabel("Upload as", { exact: true })).toHaveValue(
    "animation",
  );
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(
    page.getByText("2 frames · 243,104 pixel bytes · 60 ms per frame", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Frame delay (ms, optional)", { exact: true })
    .fill("0");
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, first frame",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(
    page.getByText("2 frames · 243,104 pixel bytes · 0 ms per frame", {
      exact: true,
    }),
  ).toBeVisible();
});
