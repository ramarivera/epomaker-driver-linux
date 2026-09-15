import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
const start = (page) =>
  page
    .getByRole("button", { name: "Start audio preview", exact: true })
    .click();
const stop = (page) =>
  page.getByRole("button", { name: "Stop audio preview", exact: true }).click();
async function setup(page, request, connected = true) {
  await request.post("/api/disconnect", { headers, data: {} });
  const calls = [];
  const control = { failStart: false, failFrame: false };
  await page.route("**/api/connect", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), light_sync: true },
    });
  });
  await page.route("**/api/audio_preview_*", async (route) => {
    const op = route.request().url().split("/").pop();
    calls.push({ op, ...route.request().postDataJSON() });
    await route.fulfill({
      json:
        op === "audio_preview_start"
          ? { session: "audio-" + calls.length }
          : op === "audio_preview_sample"
            ? {
                running: true,
                sequence: calls.length,
                bands: Array(32).fill(1),
                error: null,
              }
            : { ok: true },
    });
  });
  await page.route("**/api/live_light_*", async (route) => {
    const op = route.request().url().split("/").pop();
    calls.push({ op, ...route.request().postDataJSON() });
    if (
      (op === "live_light_start" && control.failStart) ||
      (op === "live_light_frame" && control.failFrame)
    )
      return route.fulfill({
        status: 400,
        json: {
          error:
            op === "live_light_start"
              ? "Live lighting already active"
              : "Frame transfer failed",
        },
      });
    await route.fulfill({
      json:
        op === "live_light_start"
          ? { session: "light-" + calls.length }
          : { ok: true },
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
  return { calls, control };
}
const count = (calls, op) => calls.filter((c) => c.op === op).length;
const rgbPreview = (page) =>
  page.getByRole("img", { name: "Rhythm RGB preview", exact: true });

test("offline rhythm visualization is explicit and never acquires keyboard lighting", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request, false);
  await expect(
    page.getByLabel("Send rhythm to keyboard", { exact: true }),
  ).toBeDisabled();
  expect(calls).toHaveLength(0);
  await start(page);
  await expect(rgbPreview(page)).toBeVisible();
  await expect(rgbPreview(page).locator("rect")).toHaveCount(126);
  expect(calls.some((c) => c.op.startsWith("live_light_"))).toBe(false);
  await stop(page);
  await expect(rgbPreview(page)).toHaveCount(0);
});

test("selected rhythm sends RGB frames and live controls change the next frame", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  await page.getByLabel("Rhythm mode", { exact: true }).selectOption("matrix");
  await page
    .getByLabel("Rhythm color mode", { exact: true })
    .selectOption("solid");
  await page.getByLabel("Rhythm color", { exact: true }).fill("#ff0000");
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect
    .poll(() => calls.find((c) => c.op === "live_light_frame")?.colors)
    .toBe("ff0000".repeat(126));
  expect(count(calls, "live_light_start")).toBe(1);
  await page.getByLabel("Rhythm scale", { exact: true }).fill("0");
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_frame").at(-1)?.colors)
    .toBe("000000".repeat(126));
  await stop(page);
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  await expect.poll(() => count(calls, "live_light_stop")).toBe(1);
  await expect(rgbPreview(page)).toHaveCount(0);
});

test("failure to acquire lighting stops audio capture without sending frames", async ({
  page,
  request,
}) => {
  const { calls, control } = await setup(page, request);
  control.failStart = true;
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "Live lighting already active" }),
  ).toBeVisible();
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  expect(count(calls, "live_light_frame")).toBe(0);
});

test("failed frame releases lighting and audio sessions", async ({
  page,
  request,
}) => {
  const { calls, control } = await setup(page, request);
  control.failFrame = true;
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "Frame transfer failed" }),
  ).toBeVisible();
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  await expect.poll(() => count(calls, "live_light_stop")).toBe(1);
});

test("navigation during pending lighting acquisition cleans up both sessions", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let held;
  await page.route("**/api/live_light_start", (route) => {
    held = route;
  });
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await held.fulfill({ json: { session: "late-rhythm" } });
  await expect
    .poll(() => calls.find((c) => c.op === "live_light_stop")?.session)
    .toBe("late-rhythm");
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  expect(count(calls, "live_light_frame")).toBe(0);
});

test("disconnect stops active rhythm capture and stale samples cannot send more frames", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let held;
  await page.route("**/api/audio_preview_sample", (route) => {
    held = route;
  });
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  await held.fulfill({
    json: { running: true, sequence: 1, bands: Array(32).fill(1), error: null },
  });
  await expect.poll(() => count(calls, "live_light_stop")).toBe(1);
  await page.waitForTimeout(150);
  expect(count(calls, "live_light_frame")).toBe(0);
});

test("slow frame transfer never overlaps polling and old frame errors cannot stop a new run", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let held;
  let first = true;
  await page.route("**/api/live_light_frame", async (route) => {
    if (first) {
      first = false;
      held = route;
      return;
    }
    await route.fallback();
  });
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  const samples = count(calls, "audio_preview_sample");
  await page.waitForTimeout(250);
  expect(count(calls, "audio_preview_sample")).toBe(samples);
  await stop(page);
  await expect.poll(() => count(calls, "live_light_stop")).toBe(1);
  await start(page);
  await expect.poll(() => count(calls, "live_light_frame")).toBeGreaterThan(0);
  await held.fulfill({ status: 400, json: { error: "Old frame failed" } });
  await page.waitForTimeout(150);
  await expect(
    page.getByRole("button", { name: "Stop audio preview", exact: true }),
  ).toBeEnabled();
  expect(count(calls, "audio_preview_stop")).toBe(1);
  expect(count(calls, "live_light_stop")).toBe(1);
  await expect(page.getByText("Old frame failed", { exact: true })).toHaveCount(
    0,
  );
  await stop(page);
});

test("lighting restoration failure is reported without skipping audio cleanup", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  await page.route("**/api/live_light_stop", (route) =>
    route.fulfill({
      status: 400,
      json: { error: "Lighting restoration failed" },
    }),
  );
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect(rgbPreview(page)).toBeVisible();
  await stop(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "Lighting restoration failed" }),
  ).toBeVisible();
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
});

test("capture startup without a PCM frame waits before rendering or sending", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let reads = 0;
  await page.route("**/api/audio_preview_sample", async (route) => {
    if (++reads === 1)
      return route.fulfill({
        json: { running: true, sequence: 0, bands: null, error: null },
      });
    await route.fallback();
  });
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect(rgbPreview(page)).toBeVisible();
  expect(reads).toBeGreaterThan(1);
  expect(count(calls, "audio_preview_stop")).toBe(0);
  await stop(page);
});

test("disconnect during pending lighting acquisition cancels capture and releases the late session", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let held;
  await page.route("**/api/live_light_start", (route) => {
    held = route;
  });
  await page.getByLabel("Send rhythm to keyboard", { exact: true }).check();
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect.poll(() => count(calls, "audio_preview_stop")).toBe(1);
  await held.fulfill({ json: { session: "disconnected-rhythm" } });
  await expect
    .poll(() => calls.find((c) => c.op === "live_light_stop")?.session)
    .toBe("disconnected-rhythm");
  expect(count(calls, "audio_preview_sample")).toBe(0);
  expect(count(calls, "live_light_frame")).toBe(0);
});

test("a late capture cleanup failure stays visible after cancelling startup", async ({
  page,
  request,
}) => {
  await setup(page, request, false);
  let held;
  await page.route("**/api/audio_preview_start", (route) => {
    held = route;
  });
  await page.route("**/api/audio_preview_stop", (route) =>
    route.fulfill({
      json: { ok: false, error: "Late capture cleanup failed" },
    }),
  );
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await stop(page);
  await held.fulfill({ json: { session: "cancelled-audio" } });
  await expect(
    page.getByRole("alert").filter({ hasText: "Late capture cleanup failed" }),
  ).toBeVisible();
});
