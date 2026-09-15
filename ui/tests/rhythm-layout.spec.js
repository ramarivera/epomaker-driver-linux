import { test, expect } from "@playwright/test";
import {
  RHYTHM_CANVAS,
  centerRhythmLayout,
  defaultRhythmLayout,
  resetRhythmRotation,
  resetRhythmSize,
  sampleRhythm,
  setRhythmPosition,
  setRhythmRotation,
  setRhythmSize,
} from "../src/rhythm-layout.js";

test("defaults and position clamps use the audited 640x360 source", () => {
  expect(RHYTHM_CANVAS).toEqual({ width: 640, height: 360 });
  const layout = defaultRhythmLayout();
  expect(layout).toEqual({
    x: 147,
    y: 147,
    width: 315,
    height: 90,
    rotation: 0,
  });
  expect(setRhythmPosition(layout, -100, -100)).toEqual({
    ...layout,
    x: 0,
    y: 24,
  });
  expect(setRhythmPosition(layout, 1000, 1000)).toEqual({
    ...layout,
    x: 293,
    y: 270,
  });
  expect(setRhythmPosition(layout, 10, 20)).not.toBe(layout);
});

test("size, rotation, center, and resets preserve pure layout semantics", () => {
  const layout = defaultRhythmLayout();
  const sized = setRhythmSize(layout, 1000, 1000);
  expect(sized.width).toBeGreaterThanOrEqual(90);
  expect(sized.height).toBeGreaterThanOrEqual(60);
  expect(centerRhythmLayout(sized)).toEqual(
    setRhythmPosition(
      sized,
      Math.round(304 - sized.width / 2),
      Math.round(24 + 168 - sized.height / 2),
    ),
  );
  const rotated = setRhythmRotation(layout, 45);
  expect(rotated.rotation).toBe(45);
  expect(resetRhythmRotation(rotated).rotation).toBe(0);
  expect(resetRhythmSize(rotated).width).toBe(315);
  expect(() =>
    setRhythmRotation({ ...layout, width: 600, height: 300 }, 45),
  ).toThrow(/does not fit/);
  expect(layout.rotation).toBe(0);
});

function context() {
  const calls = [];
  return {
    calls,
    save: () => calls.push(["save"]),
    restore: () => calls.push(["restore"]),
    clearRect: (...args) => calls.push(["clearRect", ...args]),
    drawImage: (...args) => calls.push(["drawImage", ...args]),
    translate: (...args) => calls.push(["translate", ...args]),
    rotate: (...args) => calls.push(["rotate", ...args]),
    getImageData: () => ({ data: new Uint8ClampedArray(21 * 6 * 4) }),
  };
}

function canvas(ctx) {
  return { width: 640, height: 360, getContext: () => ctx };
}

test("sampling clears and uses direct crop or audited rotated square crop", () => {
  const output = context();
  const source = canvas(context());
  sampleRhythm(output, source, defaultRhythmLayout());
  expect(output.calls).toEqual([
    ["save"],
    ["clearRect", 0, 0, 21, 6],
    ["drawImage", source, 147, 147, 315, 90, 0, 0, 21, 6],
    ["restore"],
  ]);

  const rotatedOutput = context();
  const scratchContext = context();
  const scratch = { width: 0, height: 0, getContext: () => scratchContext };
  sampleRhythm(
    rotatedOutput,
    source,
    setRhythmRotation(defaultRhythmLayout(), 30),
    scratch,
  );
  expect(scratch.width).toBe(Math.trunc(Math.hypot(21, 6)));
  expect(scratch.height).toBe(scratch.width);
  expect(rotatedOutput.calls.at(-1)).toEqual(["restore"]);
  expect(scratchContext.calls.some(([name]) => name === "clearRect")).toBe(
    true,
  );
});
