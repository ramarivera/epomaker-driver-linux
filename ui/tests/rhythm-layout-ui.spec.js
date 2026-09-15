import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
async function setup(page, request, connected = false) {
  await request.post("/api/disconnect", { headers, data: {} });
  const calls = [];
  await page.route("**/api/connect", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), light_sync: true },
    });
  });
  await page.route("**/api/audio_preview_*", (route) => {
    const op = route.request().url().split("/").pop();
    calls.push({ op, ...route.request().postDataJSON() });
    return route.fulfill({
      json:
        op === "audio_preview_start"
          ? { session: "layout-audio" }
          : op === "audio_preview_sample"
            ? {
                running: true,
                sequence: calls.length,
                bands: Array(32).fill(0.1),
                error: null,
              }
            : { ok: true },
    });
  });
  await page.route("**/api/live_light_*", (route) => {
    const op = route.request().url().split("/").pop();
    calls.push({ op, ...route.request().postDataJSON() });
    return route.fulfill({
      json:
        op === "live_light_start" ? { session: "layout-light" } : { ok: true },
    });
  });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  if (connected) {
    await page
      .getByLabel("Device", { exact: true })
      .selectOption({ label: "Glyph USB simulator · usb" });
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Disconnect", exact: true }),
    ).toBeEnabled();
  }
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start audio preview", exact: true }),
  ).toBeEnabled();
  return calls;
}
const field = (page, name) =>
  page.getByLabel("Rhythm " + name, { exact: true });
const button = (page, name) => page.getByRole("button", { name, exact: true });
async function defaults(page) {
  await expect(field(page, "position X")).toHaveValue("147");
  await expect(field(page, "position Y")).toHaveValue("147");
  await expect(field(page, "width")).toHaveValue("315");
  await expect(field(page, "height")).toHaveValue("90");
  await expect(field(page, "rotation")).toHaveValue("0");
}
test("offline layout controls clamp position and reset without capture or keyboard writes", async ({
  page,
  request,
}) => {
  const calls = await setup(page, request);
  await defaults(page);
  await expect(
    page.getByRole("img", { name: "Rhythm layout preview", exact: true }),
  ).toBeVisible();
  await field(page, "position X").fill("10000");
  await expect(field(page, "position X")).toHaveValue("293");
  await field(page, "position Y").fill("10000");
  await expect(field(page, "position Y")).toHaveValue("270");
  await button(page, "Reset rhythm position").click();
  await defaults(page);
  await field(page, "width").fill("100");
  await field(page, "height").fill("70");
  await field(page, "rotation").fill("90");
  await button(page, "Reset rhythm rotation").click();
  await expect(field(page, "rotation")).toHaveValue("0");
  await button(page, "Reset rhythm size").click();
  await expect(field(page, "width")).toHaveValue("315");
  await expect(field(page, "height")).toHaveValue("90");
  await button(page, "Reset rhythm layout").click();
  await defaults(page);
  expect(calls).toHaveLength(0);
});
test("rotation that cannot fit preserves the last valid layout and reports the problem", async ({
  page,
  request,
}) => {
  const calls = await setup(page, request);
  await field(page, "width").fill("500");
  await field(page, "height").fill("300");
  await field(page, "rotation").fill("90");
  await expect(field(page, "rotation")).toHaveValue("0");
  await expect(field(page, "width")).toHaveValue("500");
  await expect(field(page, "height")).toHaveValue("300");
  await expect(page.getByRole("alert")).toBeVisible();
  await button(page, "Reset rhythm layout").click();
  await defaults(page);
  expect(calls).toHaveLength(0);
});
test("live sampling follows position and size changes without opening a second session", async ({
  page,
  request,
}) => {
  const calls = await setup(page, request, true);
  await field(page, "mode").selectOption("matrix");
  await field(page, "color mode").selectOption("solid");
  await field(page, "color").fill("#00ff00");
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await button(page, "Start audio preview").click();
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_frame").length)
    .toBeGreaterThan(0);
  expect(calls.find((c) => c.op === "live_light_frame").colors).not.toBe(
    "00ff00".repeat(126),
  );
  await field(page, "width").fill("90");
  await field(page, "position X").fill("0");
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_frame").at(-1)?.colors)
    .toBe("00ff00".repeat(126));
  expect(calls.filter((c) => c.op === "live_light_start")).toHaveLength(1);
  expect(calls.filter((c) => c.op === "audio_preview_start")).toHaveLength(1);
  await field(page, "rotation").fill("90");
  await expect(field(page, "rotation")).toHaveValue("90");
  await button(page, "Stop audio preview").click();
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_stop").length)
    .toBe(1);
  await expect
    .poll(() => calls.filter((c) => c.op === "audio_preview_stop").length)
    .toBe(1);
});
