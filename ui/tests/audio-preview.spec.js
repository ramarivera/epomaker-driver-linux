import { test, expect } from "@playwright/test";
const defaults = {
  gain: 10,
  tilt: 0.5,
  contrast: 2,
  release: 0.85,
  min_db: -60,
  max_db: 0,
  attack_frames: 5,
};
const bounds = {
  gain: [1, 20, 1],
  tilt: [0, 2, 0.01],
  contrast: [0.5, 4, 0.01],
  release: [0.5, 0.99, 0.01],
  min_db: [-80, -20, 0.1],
  max_db: [-20, 20, 0.1],
  attack_frames: [1, 20, 1],
};
async function setup(page) {
  const calls = [];
  const control = { startError: null, sampleError: null, stopError: null };
  let sequence = 0;
  await page.route("**/api/audio_*", async (route) => {
    const op = route.request().url().split("/").pop();
    const data =
      route.request().method() === "POST"
        ? route.request().postDataJSON()
        : null;
    calls.push({ op, data });
    if (op === "audio_config")
      return route.fulfill({
        json: {
          defaults,
          limits: Object.fromEntries(
            Object.entries(bounds).map(([key, [min, max, step]]) => [
              key,
              { min, max, step },
            ]),
          ),
        },
      });
    if (op === "audio_outputs")
      return route.fulfill({ json: [{ id: "42", name: "Test speakers" }] });
    if (op === "audio_preview_start")
      return route.fulfill(
        control.startError
          ? { status: 400, json: { error: control.startError } }
          : { json: { session: "audio-" + calls.length } },
      );
    if (op === "audio_preview_stop")
      return route.fulfill({
        json: { ok: !control.stopError, error: control.stopError },
      });
    if (op === "audio_preview_sample")
      return route.fulfill({
        json: {
          running: !control.sampleError,
          sequence: ++sequence,
          bands: Array(32).fill(0.25),
          error: control.sampleError,
        },
      });
    throw new Error("Unexpected " + op);
  });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Lighting", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start audio preview", exact: true }),
  ).toBeEnabled();
  return { calls, control };
}
const start = (page) =>
  page
    .getByRole("button", { name: "Start audio preview", exact: true })
    .click();
const stop = (page) =>
  page.getByRole("button", { name: "Stop audio preview", exact: true }).click();
test("audio preview discovers outputs only on request and sends selected settings", async ({
  page,
}) => {
  const { calls } = await setup(page);
  expect(calls.filter((c) => c.op === "audio_outputs")).toHaveLength(0);
  await page
    .getByRole("button", { name: "Refresh audio outputs", exact: true })
    .click();
  await page.getByLabel("Audio output", { exact: true }).selectOption("42");
  await page.getByLabel("Gain", { exact: true }).fill("12");
  await start(page);
  const preview = page.getByRole("img", { name: "Audio spectrum preview" });
  await expect(preview).toBeVisible();
  await expect(preview.locator("rect")).toHaveCount(32);
  expect(calls.find((c) => c.op === "audio_preview_start").data).toEqual({
    target: "42",
    settings: { ...defaults, gain: 12 },
  });
  await expect(page.getByLabel("Gain", { exact: true })).toBeDisabled();
  await stop(page);
  await expect(preview).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Start audio preview", exact: true }),
  ).toBeEnabled();
  expect(calls.filter((c) => c.op === "audio_preview_stop")).toHaveLength(1);
  await page
    .getByRole("button", { name: "Reset audio settings", exact: true })
    .click();
  await expect(page.getByLabel("Gain", { exact: true })).toHaveValue("10");
});
test("audio start errors are actionable and do not start polling", async ({
  page,
}) => {
  const { calls, control } = await setup(page);
  control.startError = "pw-cat is not installed";
  await start(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "pw-cat is not installed" }),
  ).toBeVisible();
  expect(calls.filter((c) => c.op === "audio_preview_sample")).toHaveLength(0);
  await expect(
    page.getByRole("button", { name: "Start audio preview", exact: true }),
  ).toBeEnabled();
});
test("capture failure stops preview and reports cleanup failure", async ({
  page,
}) => {
  const { calls, control } = await setup(page);
  control.sampleError = "capture timed out";
  control.stopError = "child cleanup failed";
  await start(page);
  await expect
    .poll(() => calls.filter((c) => c.op === "audio_preview_stop").length)
    .toBe(1);
  await expect(
    page.getByRole("alert").filter({ hasText: "child cleanup failed" }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Audio spectrum preview" }),
  ).toHaveCount(0);
});
test("late audio start after navigation is stopped without polling", async ({
  page,
}) => {
  const { calls } = await setup(page);
  let held;
  await page.route("**/api/audio_preview_start", (route) => {
    held = route;
  });
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await held.fulfill({ json: { session: "late-audio" } });
  await expect
    .poll(() => calls.find((c) => c.op === "audio_preview_stop")?.data.session)
    .toBe("late-audio");
  expect(calls.filter((c) => c.op === "audio_preview_sample")).toHaveLength(0);
});
test("old audio sample errors cannot stop a newer preview", async ({
  page,
}) => {
  const { calls } = await setup(page);
  let held,
    first = true;
  await page.route("**/api/audio_preview_sample", async (route) => {
    if (first) {
      first = false;
      held = route;
      return;
    }
    await route.fallback();
  });
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await stop(page);
  await start(page);
  await expect(
    page.getByRole("img", { name: "Audio spectrum preview" }),
  ).toBeVisible();
  await held.fulfill({ status: 400, json: { error: "stale sample failure" } });
  await page.waitForTimeout(150);
  await expect(
    page.getByRole("button", { name: "Stop audio preview", exact: true }),
  ).toBeEnabled();
  expect(calls.filter((c) => c.op === "audio_preview_stop")).toHaveLength(1);
  await expect(
    page.getByText("stale sample failure", { exact: true }),
  ).toHaveCount(0);
  await stop(page);
});
