// Geometry and mode names are documented in docs/releases/glyph-rhythm-audit.md.

export const RHYTHM_MODES = Object.freeze([
  Object.freeze(["spectrum", "Spectrum"]),
  Object.freeze(["circle", "Circle"]),
  Object.freeze(["tri-cicle", "Triple circle"]),
  Object.freeze(["matrix", "Matrix"]),
  Object.freeze(["triangle", "Triangle"]),
]);

export const DEFAULT_RHYTHM_SETTINGS = Object.freeze({
  mode: "spectrum",
  scale: 100,
  colorMode: "gradient",
  color: "#ff0000",
});

const MODE_KEYS = new Set(RHYTHM_MODES.map(([key]) => key));
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function fail(message) {
  throw new TypeError(message);
}

function validateBands(bands) {
  if (!Array.isArray(bands) || bands.length !== 32)
    fail("Rhythm data must contain exactly 32 bands.");
  for (const value of bands) {
    if (!Number.isFinite(value) || value < 0 || value > 1)
      fail("Rhythm bands must be finite normalized values between 0 and 1.");
  }
}

function validateSettings(settings) {
  if (!settings || typeof settings !== "object")
    fail("Rhythm settings are required.");
  const { mode, scale, colorMode, color } = settings;
  if (!MODE_KEYS.has(mode)) fail("Unsupported rhythm mode.");
  if (!Number.isFinite(scale) || scale < 0 || scale > 100)
    fail("Rhythm scale must be between 0 and 100.");
  if (colorMode !== "solid" && colorMode !== "gradient")
    fail("Unsupported rhythm color mode.");
  if (typeof color !== "string" || !HEX_COLOR.test(color))
    fail("Rhythm color must be a six-digit hex color.");
}

function colorString(value) {
  return `rgb(${value[0]}, ${value[1]}, ${value[2]})`;
}

function animatedGradient(context, x, y, width, height, frameIndex) {
  const gradient = context.createLinearGradient(
    x,
    y + height / 2,
    x + width,
    y + height / 2,
  );
  // The vendor advances its RGB cycle once before drawing each frame.
  const frame =
    ((((Number.isFinite(frameIndex) ? Math.trunc(frameIndex) : 0) + 1) % 765) +
      765) %
    765;
  const colors =
    frame < 255
      ? [255 - frame, frame, 0]
      : frame < 510
        ? [0, 510 - frame, frame - 255]
        : [frame - 510, 0, 765 - frame];
  gradient.addColorStop(0, colorString(colors));
  gradient.addColorStop(0.5, colorString([colors[1], colors[2], colors[0]]));
  gradient.addColorStop(1, colorString([colors[2], colors[0], colors[1]]));
  return gradient;
}

function fillStyle(context, settings, bounds, frameIndex) {
  if (settings.colorMode === "solid") return settings.color;
  return animatedGradient(
    context,
    bounds.x,
    bounds.y,
    bounds.width,
    bounds.height,
    frameIndex,
  );
}

function positiveAverage(values) {
  const positive = values.filter((value) => value > 0);
  return positive.length === 0
    ? 0
    : positive.reduce((sum, value) => sum + value, 0) / positive.length;
}

function drawCircle(context, centerX, centerY, radius) {
  radius = Math.max(0, radius);
  context.beginPath();
  context.arc(centerX, centerY, radius, 0, Math.PI * 2);
  context.fill();
}

function drawTripleCircle(context, values, bounds) {
  const groups = [
    values.slice(0, 8),
    values.slice(9, 17),
    values.slice(36, 41),
  ];
  const factors = [1.5, 1.2, 1.5];
  const centerPositions = [1.5, 0.5, 2.5];
  const third = bounds.width / 3;
  groups.forEach((group, index) => {
    const radius = Math.min(
      third / 2,
      (positiveAverage(group) * third * factors[index]) / 2,
    );
    drawCircle(
      context,
      bounds.x + third * centerPositions[index],
      bounds.y + bounds.height / 2,
      radius,
    );
  });
}

function drawTriangle(context, values, bounds) {
  const groups = [
    values.slice(0, 8),
    values.slice(9, 17),
    values.slice(36, 41),
  ];
  const third = bounds.width / 3;
  groups.forEach((group, index) => {
    const left = bounds.x + third * index;
    const factors = [0.8, 1.3, 1.5];
    const height = positiveAverage(group) * bounds.height * factors[index];
    if (index === 0) context.beginPath();
    context.moveTo(left, bounds.y + bounds.height);
    context.lineTo(left + third, bounds.y + bounds.height);
    context.lineTo(left + third / 2, bounds.y + bounds.height - height);
    if (index === 2) context.closePath();
  });
  context.fill();
}

export function drawRhythm(
  context,
  bands,
  settings = DEFAULT_RHYTHM_SETTINGS,
  frameIndex = 0,
) {
  if (!context || typeof context.clearRect !== "function")
    fail("A Canvas2D context is required.");
  validateBands(bands);
  validateSettings(settings);
  const canvas = context.canvas;
  if (
    !canvas ||
    !Number.isFinite(canvas.width) ||
    !Number.isFinite(canvas.height) ||
    canvas.width < 0 ||
    canvas.height < 0
  )
    fail("Canvas dimensions must be non-negative finite numbers.");

  const scale = settings.scale / 100;
  const width = canvas.width * scale;
  const height = canvas.height * scale;
  const bounds = {
    x: (canvas.width - width) / 2,
    y: (canvas.height - height) / 2,
    width,
    height,
  };
  context.clearRect(0, 0, canvas.width, canvas.height);
  // Explicitly paint black so transparent canvas pixels never reach Glyph output.
  context.fillStyle = "#000000";
  context.fillRect(0, 0, canvas.width, canvas.height);
  if (scale === 0) return;

  context.fillStyle = fillStyle(context, settings, bounds, frameIndex);
  if (settings.mode === "spectrum") {
    const reordered = [
      ...bands.slice(29, 33).reverse(),
      ...bands.slice(0, 29),
      ...bands.slice(37),
      ...bands.slice(33, 37).reverse(),
    ];
    const barWidth = bounds.width / reordered.length;
    reordered.forEach((value, index) => {
      const barHeight = value * bounds.height;
      context.fillRect(
        bounds.x + index * barWidth,
        bounds.y + bounds.height - barHeight,
        barWidth,
        barHeight,
      );
    });
  } else if (settings.mode === "circle") {
    drawCircle(
      context,
      bounds.x + bounds.width / 2,
      bounds.y + bounds.height / 2,
      positiveAverage(bands) * bounds.width,
    );
  } else if (settings.mode === "tri-cicle") {
    drawTripleCircle(context, bands, bounds);
  } else if (settings.mode === "matrix") {
    const fraction = Math.min(positiveAverage(bands) * 2.5, 1);
    context.fillRect(
      bounds.x,
      bounds.y,
      bounds.width * fraction,
      bounds.height,
    );
  } else {
    drawTriangle(context, bands, bounds);
  }
}
