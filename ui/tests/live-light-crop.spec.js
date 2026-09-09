import { test, expect } from "@playwright/test";
import {
  centeredCrop,
  DEFAULT_RATIO,
  SCREEN_RATIOS,
} from "../src/live-light-crop.js";

test("vendor ratio choices and default are stable", () => {
  expect(SCREEN_RATIOS.map(([key]) => key)).toEqual([
    "original",
    "16:9",
    "16:10",
    "4:3",
    "1:1",
    "1.37:1",
    "1.85:1",
    "2.35:1",
  ]);
  expect(DEFAULT_RATIO).toBe("2.35:1");
});

test("centered crops match vendor geometry", () => {
  expect(centeredCrop("original", 1920, 1080)).toEqual([0, 0, 1920, 1080]);
  expect(centeredCrop("16:9", 1920, 1080)).toEqual([0, 0, 1920, 1080]);
  expect(centeredCrop("16:10", 1920, 1080)).toEqual([96, 0, 1728, 1080]);
  expect(centeredCrop("4:3", 1920, 1080)).toEqual([240, 0, 1440, 1080]);
  expect(centeredCrop(DEFAULT_RATIO, 1920, 1080)).toEqual([0, 132, 1920, 817]);
  expect(centeredCrop("1:1", 1920, 1080)).toEqual([420, 0, 1080, 1080]);
  expect(centeredCrop("1.85:1", 101, 51)).toEqual([4, 0, 94, 51]);
});

test("every supported preset returns a bounded positive rectangle", () => {
  for (const [key] of SCREEN_RATIOS) {
    const [x, y, width, height] = centeredCrop(key, 640, 480);
    expect(width).toBeGreaterThan(0);
    expect(height).toBeGreaterThan(0);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(x + width).toBeLessThanOrEqual(640);
    expect(y + height).toBeLessThanOrEqual(480);
  }
});

test("tiny inputs remain positive and invalid inputs fail", () => {
  expect(centeredCrop("2.35:1", 1, 1)).toEqual([0, 0, 1, 1]);
  expect(centeredCrop("1:1", 1, 2)).toEqual([0, 1, 1, 1]);
  for (const args of [
    ["16:9", 0, 100],
    ["16:9", 100, 0],
    ["16:9", 1.5, 100],
    ["unknown", 100, 100],
    [16 / 9, 100, 100],
  ])
    expect(() => centeredCrop(...args)).toThrow();
});
