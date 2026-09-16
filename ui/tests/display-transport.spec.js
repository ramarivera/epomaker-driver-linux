import { test, expect } from "@playwright/test";
const animation = {
  name: "two.gif",
  mimeType: "image/gif",
  buffer: Buffer.from(
    "R0lGODlhAgACAIEAAP8AAAAAAAAAAAAAACH5BAAEAAAALAAAAAACAAIAAAgGAAEIBBAQACH5BAEIAAEALAAAAAACAAIAgQAA/wAAAAAAAAAAAAgGAAEIBBAQADs=",
    "base64",
  ),
};
async function start(page) {
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
async function connect(page, label) {
  await page.getByLabel("Device", { exact: true }).selectOption({ label });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Keyboard connected.", { exact: true }),
  ).toBeVisible();
}
const still = {
  name: "pixel.png",
  mimeType: "image/png",
  buffer: Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPioAAAAASUVORK5CYII=",
    "base64",
  ),
};
async function prepare(page, kind) {
  await page
    .getByLabel("Image file", { exact: true })
    .setInputFiles(kind === "screen" ? still : animation);
  await page
    .getByRole("button", { name: "Prepare preview", exact: true })
    .click();
  await expect(
    page.getByRole("img", {
      name: "Prepared display pixels, first frame",
      exact: true,
    }),
  ).toBeVisible();
}
for (const kind of ["animation", "screen"]) {
  test(`${kind} requires connected USB, not dropdown selection`, async ({
    page,
  }) => {
    await start(page);
    await connect(page, "Glyph simulator · bluetooth");
    await prepare(page, kind);
    const upload = page.getByRole("button", {
      name: "Upload to display",
      exact: true,
    });
    await expect(upload).toBeDisabled();
    await expect(
      page.getByText(/Display uploads require wired USB/),
    ).toBeVisible();
    await page
      .getByLabel("Device", { exact: true })
      .selectOption({ label: "Glyph USB simulator · usb" });
    await expect(upload).toBeDisabled();
    await connect(page, "Glyph USB simulator · usb");
    await expect(upload).toBeEnabled();
    await upload.click();
    await expect(
      page.getByText("Image transfer finished. Check the keyboard display.", {
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(upload).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Prepare preview", exact: true }),
    ).toBeEnabled();
  });
  test(`unknown transport preserves preparation but blocks ${kind} upload`, async ({
    page,
  }) => {
    await page.route("**/api/connect", async (route) => {
      const response = await route.fetch();
      const value = await response.json();
      delete value.transport;
      await route.fulfill({ response, json: value });
    });
    await start(page);
    await connect(page, "Glyph USB simulator · usb");
    await prepare(page, kind);
    await expect(
      page.getByRole("button", { name: "Upload to display", exact: true }),
    ).toBeDisabled();
  });
}
