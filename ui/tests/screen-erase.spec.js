import { test, expect } from "@playwright/test";

const headers = { "X-Epomaker-Token": "ui-test-token" };
const button = (page, name) => page.getByRole("button", { name, exact: true });
const confirm = (page) =>
  page.getByRole("checkbox", {
    name: "I understand this erases keyboard screen storage; screen pixels cannot be backed up.",
  });
const idle = () => ({
  operation_id: null,
  state: "idle",
  active: false,
  blocked: false,
  elapsed_seconds: 0,
  completion_received: false,
  error: null,
  target_session: null,
});
const running = (session) => ({
  ...idle(),
  operation_id: "op-1",
  state: "running",
  active: true,
  blocked: true,
  elapsed_seconds: 3,
  target_session: session,
});
const json = (route, value, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(value),
  });

async function openDisplay(page, request, status) {
  await request.post("/api/disconnect", { headers, data: {} });
  if (status)
    await page.route("**/api/screen_erase", (route) => json(route, status()));
  await page.goto("/#token=ui-test-token");
  await page
    .getByRole("combobox", { name: "Device", exact: true })
    .selectOption("/dev/hidraw-usb-test");
  await button(page, "Connect").click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await button(page, "Display").click();
  await expect(button(page, "Clear keyboard screen")).toBeDisabled();
  return (await (await request.get("/api/connection", { headers })).json())
    .session;
}

test("erase survives navigation and reload while blocking device controls", async ({
  page,
  request,
}) => {
  let current = idle();
  let starts = 0;
  const session = await openDisplay(page, request, () => current);
  await page.route("**/api/screen_erase_start", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ session, confirm: true });
    starts++;
    current = running(session);
    await json(route, current);
  });
  await confirm(page).check();
  await button(page, "Clear keyboard screen").click();
  await expect(
    page.getByText("Clearing keyboard screen… 3 s elapsed."),
  ).toBeVisible();
  await expect(button(page, "Connect")).toBeDisabled();
  await expect(button(page, "Disconnect")).toBeEnabled();
  await expect(button(page, "Sync clock")).toBeDisabled();
  await expect(button(page, "Start system information refresh")).toBeDisabled();
  await button(page, "New blank draft").click();
  await expect(button(page, "Upload to display")).toBeDisabled();
  await button(page, "Settings").click();
  await expect(page.getByText(/Keyboard settings are paused/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Clearing keyboard screen/)).toBeVisible();
  await expect(button(page, "Disconnect")).toBeEnabled();
  current = {
    ...current,
    state: "completed",
    active: false,
    blocked: false,
    completion_received: true,
  };
  await button(page, "Refresh devices").click();
  await expect(
    page.getByText("Keyboard reported screen clear complete; inspect display."),
  ).toBeVisible();
  await button(page, "Display").click();
  await expect(button(page, "Sync clock")).toBeEnabled();
  expect(starts).toBe(1);
});

test("uncertain recovery requires exact acknowledgement and reconnect without resending", async ({
  page,
  request,
}) => {
  let current = idle();
  const session = await openDisplay(page, request, () => current);
  current = {
    ...running(session),
    state: "uncertain",
    active: false,
    error: "completion timeout",
  };
  let starts = 0;
  let acknowledgements = 0;
  await page.route("**/api/screen_erase_start", (route) => {
    starts++;
    return json(route, {});
  });
  await page.route("**/api/screen_erase_acknowledge", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      operation_id: "op-1",
      confirm: true,
    });
    acknowledgements++;
    await request.post("/api/disconnect", { headers, data: {} });
    current = { ...current, state: "acknowledged", blocked: false };
    await json(route, current);
  });
  await page.reload();
  await button(page, "Display").click();
  await expect(
    page.getByText("Screen erase outcome is unknown: completion timeout"),
  ).toBeVisible();
  await expect(button(page, "Acknowledge outcome")).toBeDisabled();
  await expect(button(page, "Connect")).toBeDisabled();
  await page
    .getByRole("checkbox", {
      name: "I have checked the keyboard and understand the erase outcome may be unknown.",
    })
    .check();
  await button(page, "Acknowledge outcome").click();
  await expect(
    page.getByText("Offline preview", { exact: true }),
  ).toBeVisible();
  await expect(button(page, "Disconnect")).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Device", exact: true })
    .selectOption("/dev/hidraw-usb-test");
  await expect(button(page, "Connect")).toBeEnabled();
  expect(acknowledgements).toBe(1);
  expect(starts).toBe(0);
});

test("failed start response refreshes the actual running operation", async ({
  page,
  request,
}) => {
  let current = idle();
  const session = await openDisplay(page, request, () => current);
  let starts = 0;
  await page.route("**/api/screen_erase_start", async (route) => {
    starts++;
    current = running(session);
    await json(route, { error: "response lost" }, 503);
  });
  await confirm(page).check();
  await button(page, "Clear keyboard screen").click();
  await expect(page.getByText(/Clearing keyboard screen/)).toBeVisible();
  await expect(button(page, "Clear keyboard screen")).toBeDisabled();
  await expect(button(page, "Connect")).toBeDisabled();
  expect(starts).toBe(1);
});

test("unavailable status after failed start keeps device controls locked until recovery", async ({
  page,
  request,
}) => {
  await openDisplay(page, request, idle);
  let unavailable = true;
  await page.route("**/api/screen_erase_start", async (route) => {
    await page.route("**/api/screen_erase", (statusRoute) =>
      unavailable
        ? json(statusRoute, { error: "status offline" }, 503)
        : json(statusRoute, idle()),
    );
    await json(route, { error: "start response lost" }, 503);
  });
  await confirm(page).check();
  await button(page, "Clear keyboard screen").click();
  await expect(
    page.getByText(/Screen erase status is unavailable/),
  ).toBeVisible();
  await expect(button(page, "Sync clock")).toBeDisabled();
  await expect(button(page, "Connect")).toBeDisabled();
  await expect(button(page, "Disconnect")).toBeEnabled();
  unavailable = false;
  await button(page, "Refresh devices").click();
  await expect(button(page, "Sync clock")).toBeEnabled();
});

test("real simulator completes the journaled erase through the HTTP API", async ({
  page,
  request,
}) => {
  await openDisplay(page, request);
  await confirm(page).check();
  await button(page, "Clear keyboard screen").click();
  await expect(
    page.getByText("Keyboard reported screen clear complete; inspect display."),
  ).toBeVisible({ timeout: 8000 });
  const status = await (
    await request.get("/api/screen_erase", { headers })
  ).json();
  expect(status.state).toBe("completed");
  expect(status.completion_received).toBe(true);
  expect(status.blocked).toBe(false);
  await expect(confirm(page)).not.toBeChecked();
});
