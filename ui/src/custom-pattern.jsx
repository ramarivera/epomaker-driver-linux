import React from "react";
import { Button, Field, Select } from "./controls";
import { api, download } from "./api";

export const PATTERN_SCHEMA = "epomaker-glyph-pattern";
export const PATTERN_VERSION = 1;
export const PATTERN_MODEL_ID = 3059;
export const PATTERN_COLORS = 126;
export const emptyPattern = () => Array(PATTERN_COLORS).fill("000000");

export function validatePattern(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new Error("Pattern must be a JSON object.");
  const keys = Object.keys(value).sort().join(",");
  if (keys !== "colors,model_id,schema,version")
    throw new Error("Pattern has unsupported fields.");
  if (value.schema !== PATTERN_SCHEMA)
    throw new Error("Unsupported pattern schema.");
  if (value.version !== PATTERN_VERSION)
    throw new Error("Unsupported pattern version.");
  if (value.model_id !== PATTERN_MODEL_ID)
    throw new Error("Pattern is for an unsupported model.");
  if (!Array.isArray(value.colors) || value.colors.length !== PATTERN_COLORS)
    throw new Error("Pattern must contain exactly 126 colors.");
  if (
    value.colors.some(
      (color) => typeof color !== "string" || !/^[0-9a-f]{6}$/i.test(color),
    )
  )
    throw new Error("Pattern colors must be six-digit RGB strings.");
  return value.colors.map((color) => color.toLowerCase());
}

export async function readPatternFile(file) {
  if (file.size > 64 * 1024)
    throw new Error("Pattern file exceeds the 64 KiB limit.");
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error("Pattern file is not valid JSON.");
  }
  return validatePattern(parsed);
}

export default function CustomPattern({
  index,
  setIndex,
  colors,
  setColors,
  brush,
  setBrush,
  connected,
  busy,
  run,
}) {
  const locked = busy;
  const importPattern = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    run(async () => {
      const next = await readPatternFile(file);
      setColors(next);
    }).finally(() => {
      event.target.value = "";
    });
  };
  const exportPattern = () =>
    download(`glyph-pattern-${index + 1}.json`, {
      schema: PATTERN_SCHEMA,
      version: PATTERN_VERSION,
      model_id: PATTERN_MODEL_ID,
      colors,
    });
  return (
    <>
      <div className="fields">
        <Field label="Pattern">
          <Select
            value={index}
            options={[0, 1, 2, 3, 4].map((i) => [i, `Pattern ${i + 1}`])}
            disabled={locked}
            onChange={(event) => {
              setIndex(Number(event.target.value));
              setColors(null);
            }}
          />
        </Field>
        <Field label="Paint color">
          <input
            type="color"
            value={brush}
            disabled={locked}
            onChange={(event) => setBrush(event.target.value)}
          />
        </Field>
      </div>
      <div className="fields">
        <Button
          disabled={!connected || locked}
          onClick={() => {
            const requestedIndex = index;
            run(async () => {
              const value = await api("read", {
                section: "picture",
                index: requestedIndex,
              });
              if (
                typeof value.colors !== "string" ||
                !/^[0-9a-f]{756}$/.test(value.colors)
              )
                throw new Error(
                  "Keyboard returned an invalid 126-color pattern.",
                );
              setColors(value.colors.match(/.{6}/g));
            });
          }}
        >
          Load pattern
        </Button>
        <Button disabled={locked} onClick={() => setColors(emptyPattern())}>
          New pattern
        </Button>
      </div>
      <div className="fields">
        <Field label="Import pattern JSON">
          <input
            type="file"
            accept="application/json,.json"
            disabled={locked}
            onChange={importPattern}
          />
        </Field>
      </div>
      <div className="apply-row">
        <Button disabled={locked || !colors} onClick={exportPattern}>
          Export pattern JSON
        </Button>
        <Button
          disabled={locked || !colors}
          onClick={() => setColors(colors.map(() => brush.slice(1)))}
        >
          Fill all
        </Button>
      </div>
      <p className="muted">
        Import/export Glyph pattern JSON. Vendor configuration files use a
        different format.
      </p>
      {colors && (
        <div className="color-grid">
          {colors.map((color, i) => (
            <button
              key={i}
              title={`Color slot ${i}`}
              aria-label={`Color slot ${i}`}
              disabled={locked}
              style={{ background: `#${color}` }}
              onClick={() =>
                setColors(
                  colors.map((current, j) =>
                    i === j ? brush.slice(1) : current,
                  ),
                )
              }
            />
          ))}
        </div>
      )}
      <Button
        disabled={!connected || locked || !colors}
        onClick={() =>
          run(
            () =>
              api("write", { kind: "picture", index, colors: colors.join("") }),
            "Pattern verified.",
          )
        }
      >
        Save pattern
      </Button>
      <p className="muted">
        Saving does not select an effect. To display this bank, choose User
        picture and the matching pattern in main lighting, then apply lighting.
      </p>
    </>
  );
}
