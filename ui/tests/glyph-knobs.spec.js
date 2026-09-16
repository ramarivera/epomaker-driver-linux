import { test, expect } from "@playwright/test";

const headers = { "X-Epomaker-Token": "ui-test-token" };

test("Glyph knobs reject Fn and held assignments while ordinary keys retain both", async ({
  page,
  request,
}) => {
  await request.post("/api/disconnect", { headers, data: {} });
  await page.goto("/#token=ui-test-token");
  await expect(
    page.getByRole("button", { name: "Refresh devices", exact: true }),
  ).toBeEnabled();
  await page
    .getByLabel("Device", { exact: true })
    .selectOption("/dev/hidraw-test");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const apply = page.getByRole("button", {
    name: "Apply to keyboard",
    exact: true,
  });
  await expect(apply).toBeEnabled();
  for (const [name, slot] of [
    ["AudioVolumeDown", 109],
    ["MediaPlayPause", 53],
    ["AudioVolumeUp", 108],
  ]) {
    await page
      .getByRole("button", { name: `Key ${name}`, exact: true })
      .click();
    await page.getByLabel("Action", { exact: true }).selectOption("Macro");
    await expect(
      page.getByLabel("Playback").locator('option[value="2"]'),
    ).toBeDisabled();
    await page.getByLabel("Playback").selectOption("1");
    await apply.click();
    await expect(apply).toBeEnabled();
    const read = await (
      await request.post("/api/read", { headers, data: { section: "keymap" } })
    ).json();
    expect(read.raw.slice(slot * 4, slot * 4 + 4)).toEqual([9, 1, 0, 0]);
    await page.getByLabel("Action", { exact: true }).selectOption("Raw");
    await page.getByLabel("Four-byte action").fill("09 02 00 01");
    await expect(apply).toBeEnabled();
    await page.getByLabel("Four-byte action").fill("09 02 00 00");
    await expect(apply).toBeDisabled();
    await expect(
      page.getByText(/Knob inputs cannot use held macro playback/),
    ).toBeVisible();
    for (const layer of ["Fn Windows", "Fn Mac"]) {
      await page.getByRole("button", { name: layer, exact: true }).click();
      await expect(
        page.getByText(/Knob inputs have no editable Fn assignment/),
      ).toBeVisible();
      await expect(apply).toBeDisabled();
      for (const knob of [
        "AudioVolumeDown",
        "MediaPlayPause",
        "AudioVolumeUp",
      ]) {
        await expect(
          page.getByRole("button", { name: `Key ${knob}`, exact: true }),
        ).toBeDisabled();
      }
    }
    await page.getByRole("button", { name: "Key A", exact: true }).click();
    await expect(apply).toBeEnabled();
    await page.getByLabel("Action", { exact: true }).selectOption("Macro");
    await page.getByLabel("Playback").selectOption("2");
    await apply.click();
    await expect(apply).toBeEnabled();
    await page.getByRole("button", { name: "Main", exact: true }).click();
    await expect(apply).toBeEnabled();
  }
});
