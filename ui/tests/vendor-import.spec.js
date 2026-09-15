import { test, expect } from "@playwright/test";

const headers = { "X-Epomaker-Token": "ui-test-token" };
const payload = (fn = false) => ({
  deviceType: { id: 3059 },
  fn,
  value: [
    {
      type: "ConfigMacro",
      original: 4,
      macroType: "on_off",
      repeatCount: 1,
      macro: [],
    },
  ],
});
async function open(page, request) {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await page
    .getByLabel("Device", { exact: true })
    .selectOption("/dev/hidraw-test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply to keyboard", exact: true }),
  ).toBeEnabled();
}
async function upload(page, value) {
  await page
    .getByLabel("Vendor configuration file", { exact: true })
    .setInputFiles({
      name: "vendor.dat",
      mimeType: "application/octet-stream",
      buffer: Buffer.from(JSON.stringify(value)),
    });
  await page
    .getByRole("button", { name: "Preview import", exact: true })
    .click();
}
for (const target of ["Main", "Fn Mac"]) {
  test(`imports ${target} vendor macros through the simulator`, async ({
    page,
    request,
  }) => {
    await open(page, request);
    await page.getByRole("button", { name: target, exact: true }).click();
    await upload(page, payload(target !== "Main"));
    await expect(
      page.getByText("Preview ready. No keyboard settings have changed.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(`Target: ${target} · Profile 1`, { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Apply preview to keyboard", exact: true })
      .click();
    await expect(
      page.getByText(/Imported configuration. Recovery copy:/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "Apply preview to keyboard",
        exact: true,
      }),
    ).toBeDisabled();
    const catalog = await (
      await request.get("/api/catalog", { headers })
    ).json();
    const slot = Array.from({ length: 128 }, (_, n) => n).find(
      (n) => catalog.matrices[0].slice(n * 4, n * 4 + 4).join() === "0,0,4,0",
    );
    const read = await (
      await request.post("/api/read", {
        headers,
        data: {
          section: "keymap",
          fn: target !== "Main",
          os_mode: target === "Fn Mac" ? 1 : 0,
        },
      })
    ).json();
    expect(read.raw.slice(slot * 4, slot * 4 + 4)).toEqual([9, 1, 0, 0]);
    const macro = await (
      await request.post("/api/read", {
        headers,
        data: { section: "macro", slot: 0 },
      })
    ).json();
    expect(macro.data).toBe("0100" + "00".repeat(254));
  });
}
test("invalid files cannot be applied and changing profile discards a preview", async ({
  page,
  request,
}) => {
  await open(page, request);
  await upload(page, payload());
  const apply = page.getByRole("button", {
    name: "Apply preview to keyboard",
    exact: true,
  });
  await expect(apply).toBeEnabled();
  await page.getByLabel("Profile", { exact: true }).selectOption("1");
  await expect(apply).toBeDisabled();
  await upload(page, { bad: true });
  await expect(page.getByRole("alert")).toContainText("action list");
  await expect(apply).toBeDisabled();
});
test("late preview response cannot restore the previous layer token", async ({
  page,
  request,
}) => {
  await open(page, request);
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  let started;
  const reached = new Promise((resolve) => {
    started = resolve;
  });
  await page.route("**/api/vendor_import_preview", async (route) => {
    started();
    await pending;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        token: "old",
        plan: {
          target: "Main",
          profile: 0,
          assignments: [],
          macros: {},
          reserved_slots: [],
        },
      }),
    });
  });
  await upload(page, payload());
  await reached;
  await page.getByRole("button", { name: "Fn Mac", exact: true }).click();
  release();
  await expect(
    page.getByRole("button", { name: "Preview import", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", {
      name: "Apply preview to keyboard",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(page.getByText(/Preview ready/)).toHaveCount(0);
});
