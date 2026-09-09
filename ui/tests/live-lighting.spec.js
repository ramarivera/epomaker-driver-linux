import { test, expect } from "@playwright/test";
const headers = { "X-Epomaker-Token": "ui-test-token" };
async function setup(page, request, mode = "normal") {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.addInitScript((mode) => {
    window.captureCalls = 0;
    window.liveTracks = [];
    window.liveVideoSize = [1920, 1080];
    window.liveDrawCalls = [];
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", {
      configurable: true,
      get: () => window.liveVideoSize[0],
    });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", {
      configurable: true,
      get: () => window.liveVideoSize[1],
    });
    const makeStream = () => {
      const source = document.createElement("canvas");
      const stream = source.captureStream(1);
      window.liveTracks.push(...stream.getTracks());
      return stream;
    };
    Object.defineProperty(navigator.mediaDevices, "getDisplayMedia", {
      configurable: true,
      value: () => {
        window.captureCalls++;
        if (mode === "deny") return Promise.reject(new Error("capture denied"));
        if (mode === "permission")
          return new Promise((resolve) => {
            window.resolveCapture = () => resolve(makeStream());
          });
        return Promise.resolve(makeStream());
      },
    });
    HTMLMediaElement.prototype.play = function () {
      if (mode === "play")
        return new Promise((resolve) => {
          window.resolvePlay = resolve;
        });
      return Promise.resolve();
    };
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (...args) {
      if (this.width !== 21 || this.height !== 6)
        return original.apply(this, args);
      return {
        drawImage(...args) {
          window.liveDrawCalls.push(args.slice(1));
        },
        getImageData() {
          const data = new Uint8ClampedArray(21 * 6 * 4);
          for (let i = 0; i < data.length; i += 4)
            data.set([255, 20, 60, 128], i);
          return { data };
        },
      };
    };
  }, mode);
  await page.route("**/api/connect", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), light_sync: true },
    });
  });
  const calls = [];
  const control = { failFrame: false };
  await page.route("**/api/live_light_*", async (route) => {
    const op = route.request().url().split("/").pop();
    calls.push({ op, ...route.request().postDataJSON() });
    if (op === "live_light_frame" && control.failFrame) {
      await route.fulfill({ status: 500, json: { error: "frame failed" } });
      return;
    }
    await route.fulfill({
      json:
        op === "live_light_start"
          ? { session: "session-" + calls.length }
          : { ok: true },
    });
  });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page
    .getByLabel("Device", { exact: true })
    .selectOption({ label: "Glyph USB simulator · usb" });
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start screen lighting", exact: true }),
  ).toBeEnabled();
  return { calls, control };
}
const start = (page) =>
  page
    .getByRole("button", { name: "Start screen lighting", exact: true })
    .click();
const stop = (page) =>
  page
    .getByRole("button", { name: "Stop screen lighting", exact: true })
    .click();
async function tracksEnded(page) {
  await expect
    .poll(() =>
      page.evaluate(() =>
        window.liveTracks.every((t) => t.readyState === "ended"),
      ),
    )
    .toBe(true);
}
test("live screen start sends RGB in order and stop cleans up", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  await start(page);
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_frame").length)
    .toBeGreaterThan(0);
  expect(calls.find((c) => c.op === "live_light_frame").colors).toBe(
    "800a1e".repeat(126),
  );
  await stop(page);
  await tracksEnded(page);
  await expect.poll(() => calls.at(-1)?.op).toBe("live_light_stop");
  const n = calls.length;
  await page.waitForTimeout(250);
  expect(calls).toHaveLength(n);
});
test("capture permission denial creates no backend session", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request, "deny");
  await start(page);
  await expect(page.getByText("capture denied", { exact: true })).toBeVisible();
  expect(calls).toHaveLength(0);
  await expect(
    page.getByRole("button", { name: "Start screen lighting", exact: true }),
  ).toBeEnabled();
});
test("disconnect cancels pending capture and stops late tracks", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request, "permission");
  await start(page);
  await expect(
    page.getByRole("button", { name: "Start screen lighting", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Connect", exact: true }),
  ).toBeEnabled();
  await page.evaluate(() => window.resolveCapture());
  await tracksEnded(page);
  expect(await page.evaluate(() => window.captureCalls)).toBe(1);
  expect(calls).toHaveLength(0);
});
test("leaving page while video play is pending prevents backend start", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request, "play");
  await start(page);
  await expect
    .poll(() => page.evaluate(() => typeof window.resolvePlay))
    .toBe("function");
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await tracksEnded(page);
  await page.evaluate(() => window.resolvePlay());
  expect(calls).toHaveLength(0);
});
test("frame error and ended capture stop their sessions", async ({
  page,
  request,
}) => {
  const { calls, control } = await setup(page, request);
  control.failFrame = true;
  await start(page);
  await expect(page.getByText("frame failed", { exact: true })).toBeVisible();
  await tracksEnded(page);
  await expect.poll(() => calls.at(-1)?.op).toBe("live_light_stop");
  control.failFrame = false;
  await start(page);
  await expect(page.getByText(/Capturing screen/)).toBeVisible();
  await page.evaluate(() =>
    window.liveTracks.at(-1).dispatchEvent(new Event("ended")),
  );
  await expect(
    page.getByText("Screen capture ended.", { exact: true }),
  ).toBeVisible();
  await tracksEnded(page);
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_stop").length)
    .toBe(2);
});
test("navigation stops active capture and restores through stop API", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  await start(page);
  await expect
    .poll(() => calls.filter((c) => c.op === "live_light_frame").length)
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await tracksEnded(page);
  await expect.poll(() => calls.at(-1)?.op).toBe("live_light_stop");
});

test("late frame failure cannot stop a newer capture", async ({
  page,
  request,
}) => {
  await setup(page, request);
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
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await stop(page);
  await start(page);
  await expect(page.getByText(/Capturing screen · [1-9]/)).toBeVisible();
  await held.fulfill({ status: 500, json: { error: "old frame failed" } });
  await page.waitForTimeout(200);
  await expect(
    page.getByRole("button", { name: "Stop screen lighting", exact: true }),
  ).toBeEnabled();
  expect(await page.evaluate(() => window.liveTracks.at(-1).readyState)).toBe(
    "live",
  );
  await expect(page.getByText("old frame failed", { exact: true })).toHaveCount(
    0,
  );
  await stop(page);
});

test("backend session created after navigation is explicitly stopped", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  let held;
  await page.route("**/api/live_light_start", (route) => {
    held = route;
  });
  await start(page);
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Keymap", exact: true }).click();
  await tracksEnded(page);
  await held.fulfill({ json: { session: "late-session" } });
  await expect
    .poll(() => calls.find((c) => c.op === "live_light_stop")?.session)
    .toBe("late-session");
  expect(calls.filter((c) => c.op === "live_light_frame")).toHaveLength(0);
});

test("screen crop ratio updates frames and preview without recapturing", async ({
  page,
  request,
}) => {
  const { calls } = await setup(page, request);
  const ratio = page.getByLabel("Screen crop ratio", { exact: true });
  await expect(ratio).toHaveValue("2.35:1");
  await ratio.selectOption("1:1");
  await start(page);
  await expect
    .poll(() => page.evaluate(() => window.liveDrawCalls.at(-1)))
    .toEqual([420, 0, 1080, 1080, 0, 0, 21, 6]);
  const preview = page.getByRole("img", {
    name: "Live RGB color preview, 21 columns by 6 rows",
  });
  await expect(preview).toBeVisible();
  await expect(preview.locator("rect")).toHaveCount(126);
  await expect(preview.locator("rect").first()).toHaveAttribute(
    "fill",
    "#800a1e",
  );
  await ratio.selectOption("original");
  await expect
    .poll(() => page.evaluate(() => window.liveDrawCalls.at(-1)))
    .toEqual([0, 0, 1920, 1080, 0, 0, 21, 6]);
  await ratio.selectOption("1:1");
  await page.evaluate(() => {
    window.liveVideoSize = [1000, 2000];
  });
  await expect
    .poll(() => page.evaluate(() => window.liveDrawCalls.at(-1)))
    .toEqual([0, 500, 1000, 1000, 0, 0, 21, 6]);
  await expect(
    page.getByText("Source 1000×2000 · Crop 1000×1000 at 0, 500", {
      exact: true,
    }),
  ).toBeVisible();
  expect(calls.filter((c) => c.op === "live_light_start")).toHaveLength(1);
  expect(await page.evaluate(() => window.captureCalls)).toBe(1);
  await stop(page);
  await expect(preview).toHaveCount(0);
});

test("screen crop selection survives page changes and resets to vendor default", async ({
  page,
  request,
}) => {
  await setup(page, request);
  await page
    .getByLabel("Screen crop ratio", { exact: true })
    .selectOption("16:10");
  await page.getByRole("button", { name: "Display", exact: true }).click();
  await page.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(
    page.getByLabel("Screen crop ratio", { exact: true }),
  ).toHaveValue("16:10");
  await page
    .getByRole("button", { name: "Reset screen crop ratio", exact: true })
    .click();
  await expect(
    page.getByLabel("Screen crop ratio", { exact: true }),
  ).toHaveValue("2.35:1");
  expect(await page.evaluate(() => window.captureCalls)).toBe(0);
});
