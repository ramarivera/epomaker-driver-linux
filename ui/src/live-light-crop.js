export const SCREEN_RATIOS = Object.freeze([
  Object.freeze(["original", "Original"]),
  Object.freeze(["16:9", "16:9"]),
  Object.freeze(["16:10", "16:10"]),
  Object.freeze(["4:3", "4:3"]),
  Object.freeze(["1:1", "1:1"]),
  Object.freeze(["1.37:1", "1.37:1"]),
  Object.freeze(["1.85:1", "1.85:1"]),
  Object.freeze(["2.35:1", "2.35:1"]),
]);

export const DEFAULT_RATIO = "2.35:1";

function invalid(message) {
  throw new Error(message);
}

function ratioValue(key) {
  const option = SCREEN_RATIOS.find(([value]) => value === key);
  if (!option) invalid("Unsupported screen ratio.");
  if (option[0] === "original") return null;
  const [numerator, denominator] = option[0].split(":");
  return Number(numerator) / Number(denominator);
}

export function centeredCrop(key, sourceWidth, sourceHeight) {
  if (
    !Number.isSafeInteger(sourceWidth) ||
    !Number.isSafeInteger(sourceHeight) ||
    sourceWidth <= 0 ||
    sourceHeight <= 0
  )
    invalid("Source dimensions must be positive safe integers.");
  const ratio = ratioValue(key);
  if (ratio === null) return [0, 0, sourceWidth, sourceHeight];

  const sourceRatio = sourceWidth / sourceHeight;
  let width = sourceWidth;
  let height = sourceHeight;
  if (ratio > sourceRatio) height = Math.round(sourceWidth / ratio);
  else width = Math.round(sourceHeight * ratio);
  width = Math.max(1, Math.min(sourceWidth, width));
  height = Math.max(1, Math.min(sourceHeight, height));
  return [
    Math.round((sourceWidth - width) / 2),
    Math.round((sourceHeight - height) / 2),
    width,
    height,
  ];
}
