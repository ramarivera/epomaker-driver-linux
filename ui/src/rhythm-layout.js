// Geometry audited against docs/releases/glyph-rhythm-layout-audit.md.

export const RHYTHM_CANVAS = Object.freeze({ width: 640, height: 360 });

const OUTPUT_WIDTH = 21;
const OUTPUT_HEIGHT = 6;
const MIN_WIDTH = 90;
const MIN_HEIGHT = 60;
const DEFAULT_WIDTH = 315;
const DEFAULT_HEIGHT = 90;
const TOP_PADDING = 24;
const RIGHT_PADDING = 32;

function fail(message) {
  throw new TypeError(message);
}

function finite(value, name) {
  if (!Number.isFinite(value)) fail(`${name} must be a finite number.`);
}

function validateLayout(layout) {
  if (!layout || typeof layout !== "object")
    fail("A rhythm layout is required.");
  for (const name of ["x", "y", "width", "height", "rotation"])
    finite(layout[name], `layout.${name}`);
  if (layout.width < MIN_WIDTH || layout.height < MIN_HEIGHT)
    fail(`Layout dimensions must be at least ${MIN_WIDTH}x${MIN_HEIGHT}.`);
  if (layout.rotation < -180 || layout.rotation > 180)
    fail("Layout rotation must be between -180 and 180 degrees.");
}

function rotatedBounds(width, height, rotation) {
  const radians = (rotation * Math.PI) / 180;
  const cosine = Math.abs(Math.cos(radians));
  const sine = Math.abs(Math.sin(radians));
  return {
    rotatedW: width * cosine + height * sine,
    rotatedH: width * sine + height * cosine,
  };
}

function clampPosition(x, y, width, height, rotation) {
  const { rotatedW, rotatedH } = rotatedBounds(width, height, rotation);
  const xOffset = (rotatedW - width) / 2;
  const yOffset = (rotatedH - height) / 2;
  const xMin = xOffset;
  const xMax = RHYTHM_CANVAS.width - width - xOffset - RIGHT_PADDING;
  const yMin = TOP_PADDING + yOffset;
  const yMax = RHYTHM_CANVAS.height - height - yOffset;
  return {
    x: Math.max(xMin, Math.min(x, xMax)),
    y: Math.max(yMin, Math.min(y, yMax)),
  };
}

function withPosition(layout, x, y) {
  validateLayout(layout);
  finite(x, "x");
  finite(y, "y");
  const position = clampPosition(
    x,
    y,
    layout.width,
    layout.height,
    layout.rotation,
  );
  return { ...layout, ...position };
}

export function defaultRhythmLayout() {
  const x = Math.round(
    (RHYTHM_CANVAS.width - RIGHT_PADDING) / 2 - DEFAULT_WIDTH / 2,
  );
  const y = Math.round(
    TOP_PADDING + (RHYTHM_CANVAS.height - TOP_PADDING) / 2 - DEFAULT_HEIGHT / 2,
  );
  return { x, y, width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT, rotation: 0 };
}

export default defaultRhythmLayout;

export function setRhythmPosition(layout, x, y) {
  return withPosition(layout, x, y);
}

export function setRhythmSize(layout, width, height) {
  validateLayout(layout);
  finite(width, "width");
  finite(height, "height");
  const requestedWidth = Math.max(width, MIN_WIDTH);
  const requestedHeight = Math.max(height, MIN_HEIGHT);
  const availableWidth = RHYTHM_CANVAS.width - RIGHT_PADDING;
  const availableHeight = RHYTHM_CANVAS.height - TOP_PADDING;
  const bounds = rotatedBounds(
    requestedWidth,
    requestedHeight,
    layout.rotation,
  );
  let nextWidth = requestedWidth;
  let nextHeight = requestedHeight;
  if (bounds.rotatedW > availableWidth || bounds.rotatedH > availableHeight) {
    const scale = Math.min(
      availableWidth / bounds.rotatedW,
      availableHeight / bounds.rotatedH,
      1,
    );
    nextWidth = Math.max(Math.floor(requestedWidth * scale), MIN_WIDTH);
    nextHeight = Math.max(Math.floor(requestedHeight * scale), MIN_HEIGHT);
  }
  return withPosition(
    { ...layout, width: nextWidth, height: nextHeight },
    layout.x,
    layout.y,
  );
}

export function setRhythmRotation(layout, degrees) {
  validateLayout(layout);
  finite(degrees, "rotation");
  if (degrees < -180 || degrees > 180)
    fail("Rhythm rotation must be between -180 and 180 degrees.");
  const bounds = rotatedBounds(layout.width, layout.height, degrees);
  if (
    bounds.rotatedW > RHYTHM_CANVAS.width - RIGHT_PADDING ||
    bounds.rotatedH > RHYTHM_CANVAS.height - TOP_PADDING
  )
    throw new RangeError(
      "Rhythm rotation does not fit within the source canvas.",
    );
  return withPosition({ ...layout, rotation: degrees }, layout.x, layout.y);
}

export function centerRhythmLayout(layout) {
  validateLayout(layout);
  return withPosition(
    layout,
    Math.round((RHYTHM_CANVAS.width - RIGHT_PADDING) / 2 - layout.width / 2),
    Math.round(
      TOP_PADDING +
        (RHYTHM_CANVAS.height - TOP_PADDING) / 2 -
        layout.height / 2,
    ),
  );
}

export function resetRhythmSize(layout) {
  validateLayout(layout);
  return setRhythmSize(layout, DEFAULT_WIDTH, DEFAULT_HEIGHT);
}

export function resetRhythmRotation(layout) {
  return setRhythmRotation(layout, 0);
}

function validateCanvas(canvas, name) {
  if (
    !canvas ||
    typeof canvas !== "object" ||
    typeof canvas.getContext !== "function"
  )
    fail(`${name} must be a canvas.`);
}

function readOutputs(context) {
  const data = context.getImageData(0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT).data;
  const output = [];
  for (let index = 0; index < data.length; index += 4) {
    const alpha = data[index + 3] / 255;
    output.push(
      data[index] * alpha,
      data[index + 1] * alpha,
      data[index + 2] * alpha,
    );
  }
  return output;
}

export function sampleRhythm(
  outputContext,
  sourceCanvas,
  layout,
  scratchCanvas,
) {
  if (
    !outputContext ||
    typeof outputContext.clearRect !== "function" ||
    typeof outputContext.drawImage !== "function"
  )
    fail("A Canvas2D output context is required.");
  validateCanvas(sourceCanvas, "sourceCanvas");
  validateLayout(layout);
  if (layout.rotation !== 0) validateCanvas(scratchCanvas, "scratchCanvas");
  outputContext.save?.();
  try {
    outputContext.setTransform?.(1, 0, 0, 1, 0, 0);
    outputContext.clearRect(0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT);
    if (layout.rotation === 0) {
      outputContext.drawImage(
        sourceCanvas,
        layout.x,
        layout.y,
        layout.width,
        layout.height,
        0,
        0,
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT,
      );
    } else {
      const scratchContext = scratchCanvas.getContext("2d", {
        willReadFrequently: true,
      });
      if (!scratchContext)
        fail("scratchCanvas must provide a Canvas2D context.");
      const sourceDiagonal = Math.hypot(layout.width, layout.height);
      const outputDiagonal = Math.hypot(OUTPUT_WIDTH, OUTPUT_HEIGHT);
      scratchCanvas.width = Math.trunc(outputDiagonal);
      scratchCanvas.height = Math.trunc(outputDiagonal);
      scratchContext.save?.();
      scratchContext.translate(outputDiagonal / 2, outputDiagonal / 2);
      scratchContext.rotate(((360 - layout.rotation) * Math.PI) / 180);
      scratchContext.clearRect(
        -outputDiagonal / 2,
        -outputDiagonal / 2,
        outputDiagonal,
        outputDiagonal,
      );
      scratchContext.drawImage(
        sourceCanvas,
        layout.x + layout.width / 2 - sourceDiagonal / 2,
        layout.y + layout.height / 2 - sourceDiagonal / 2,
        sourceDiagonal,
        sourceDiagonal,
        -outputDiagonal / 2,
        -outputDiagonal / 2,
        outputDiagonal,
        outputDiagonal,
      );
      scratchContext.restore?.();
      outputContext.drawImage(
        scratchCanvas,
        (outputDiagonal - OUTPUT_WIDTH) / 2,
        (outputDiagonal - OUTPUT_HEIGHT) / 2,
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT,
        0,
        0,
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT,
      );
    }
    return readOutputs(outputContext);
  } finally {
    outputContext.restore?.();
  }
}
