import { test, expect } from "@playwright/test";
import {
  DEFAULT_RHYTHM_SETTINGS,
  RHYTHM_MODES,
  drawRhythm,
} from "../src/rhythm-renderer.js";

function recordingContext(width = 420, height = 120) {
  const calls = [];
  const context = {
    canvas: { width, height },
    calls,
    fillStyle: null,
    clearRect(...args) {
      calls.push(["clearRect", ...args]);
    },
    fillRect(...args) {
      calls.push(["fillRect", ...args, this.fillStyle]);
    },
    createLinearGradient(...args) {
      const gradient = {
        stops: [],
        addColorStop(offset, color) {
          this.stops.push([offset, color]);
        },
      };
      calls.push(["createLinearGradient", ...args, gradient]);
      return gradient;
    },
    beginPath() {
      calls.push(["beginPath"]);
    },
    arc(...args) {
      calls.push(["arc", ...args]);
    },
    moveTo(...args) {
      calls.push(["moveTo", ...args]);
    },
    lineTo(...args) {
      calls.push(["lineTo", ...args]);
    },
    closePath() {
      calls.push(["closePath"]);
    },
    fill() {
      calls.push(["fill", this.fillStyle]);
    },
  };
  return context;
}

const bands = Array.from({ length: 32 }, (_, index) => index / 31);
const solid = {
  mode: "spectrum",
  scale: 100,
  colorMode: "solid",
  color: "#123456",
};

test("exports vendor rhythm modes and defaults", () => {
  expect(RHYTHM_MODES.map(([key]) => key)).toEqual([
    "spectrum",
    "circle",
    "tri-cicle",
    "matrix",
    "triangle",
  ]);
  expect(DEFAULT_RHYTHM_SETTINGS).toEqual({
    mode: "spectrum",
    scale: 100,
    colorMode: "gradient",
    color: "#ff0000",
  });
});

test("spectrum reorders the final three 32-band values and scales bars", () => {
  const context = recordingContext();
  drawRhythm(context, bands, solid);
  const bars = context.calls.filter(([name]) => name === "fillRect").slice(1);
  expect(bars).toHaveLength(32);
  expect(bars[0].slice(1, 5)).toEqual([0, 0, 420 / 32, (31 / 31) * 120]);
  expect(bars[3].slice(1, 5)).toEqual([
    3 * (420 / 32),
    120 - (0 / 31) * 120,
    420 / 32,
    0,
  ]);
  expect(bars[31].slice(1, 5)).toEqual([
    31 * (420 / 32),
    120 - (28 / 31) * 120,
    420 / 32,
    (28 / 31) * 120,
  ]);
});

test("all five modes draw from the supplied canvas and gradient has three stops", () => {
  for (const [mode] of RHYTHM_MODES) {
    const context = recordingContext();
    drawRhythm(context, bands, { ...DEFAULT_RHYTHM_SETTINGS, mode }, 7);
    expect(context.calls[0]).toEqual(["clearRect", 0, 0, 420, 120]);
    expect(
      context.calls.some(([name]) => name === "createLinearGradient"),
    ).toBe(true);
    const gradient = context.calls.find(
      ([name]) => name === "createLinearGradient",
    )[5];
    expect(gradient.stops).toHaveLength(3);
    expect(
      context.calls.some(([name]) => name === "fill" || name === "fillRect"),
    ).toBe(true);
  }
});

test("scale zero leaves an opaque black canvas with no geometry", () => {
  const context = recordingContext();
  drawRhythm(context, bands, { ...solid, scale: 0 });
  expect(context.calls).toEqual([
    ["clearRect", 0, 0, 420, 120],
    ["fillRect", 0, 0, 420, 120, "#000000"],
  ]);
});

test("empty positive groups are silent and invalid inputs fail clearly", () => {
  const context = recordingContext();
  drawRhythm(context, Array(32).fill(0), { ...solid, mode: "tri-cicle" });
  expect(
    context.calls.filter(([name]) => name === "arc").map((call) => call[3]),
  ).toEqual([0, 0, 0]);
  for (const [invalidBands, invalidSettings] of [
    [Array(31).fill(0), solid],
    [[...bands.slice(0, 31), Number.NaN], solid],
    [bands, { ...solid, mode: "unknown" }],
    [bands, { ...solid, color: "red" }],
  ]) {
    expect(() =>
      drawRhythm(recordingContext(), invalidBands, invalidSettings),
    ).toThrow();
  }
});

test("circle radii and triangle heights follow the audited formulas", () => {
  const circle = recordingContext();
  drawRhythm(circle, Array(32).fill(0.25), { ...solid, mode: "circle" });
  expect(circle.calls.find((c) => c[0] === "arc").slice(1, 4)).toEqual([
    210, 60, 105,
  ]);
  const triple = recordingContext();
  drawRhythm(triple, Array(32).fill(0.25), { ...solid, mode: "tri-cicle" });
  expect(
    triple.calls.filter((c) => c[0] === "arc").map((c) => c.slice(1, 4)),
  ).toEqual([
    [210, 60, 26.25],
    [70, 60, 21],
    [350, 60, 0],
  ]);
  const triangles = recordingContext();
  drawRhythm(triangles, Array(32).fill(1), { ...solid, mode: "triangle" });
  const lines = triangles.calls.filter((c) => c[0] === "lineTo");
  expect(lines[1]).toEqual(["lineTo", 70, 24]);
  expect(lines[3]).toEqual(["lineTo", 210, -36]);
  expect(lines[5]).toEqual(["lineTo", 350, 120]);
});

test("gradient cycles through RGB endpoints and advances before drawing", () => {
  const stopsAt = (frame) => {
    const context = recordingContext();
    drawRhythm(context, Array(32).fill(0.5), DEFAULT_RHYTHM_SETTINGS, frame);
    return context.calls.find((c) => c[0] === "createLinearGradient")[5].stops;
  };
  expect(stopsAt(0)).toEqual([
    [0, "rgb(254, 1, 0)"],
    [0.5, "rgb(1, 0, 254)"],
    [1, "rgb(0, 254, 1)"],
  ]);
  expect(stopsAt(254)[0][1]).toBe("rgb(0, 255, 0)");
  expect(stopsAt(509)[0][1]).toBe("rgb(0, 0, 255)");
  expect(stopsAt(764)[0][1]).toBe("rgb(255, 0, 0)");
  expect(stopsAt(765)).toEqual(stopsAt(0));
});
