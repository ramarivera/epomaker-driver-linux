import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select, titleCase } from "./controls";
const initial = {
  mode: "solid",
  rgb: 0xffffff,
  brightness: 4,
  speed: 0,
  option: 0,
  rainbow: false,
};
export default function Lighting({
  catalog,
  ui: descriptor,
  connected,
  busy,
  run,
  epoch,
}) {
  const [side, setSide] = useState(false),
    [lights, setLights] = useState({ main: initial, side: initial });
  const [index, setIndex] = useState(0),
    [colors, setColors] = useState(null),
    [brush, setBrush] = useState("#365df5");
  const key = side ? "side" : "main",
    value = lights[key];
  const ui = descriptor || catalog?.ui || {};
  const controls = ui.controls;
  const hasSide = controls
    ? controls.includes("side_lighting")
    : Boolean(catalog.side_modes);
  const pictureSlots = Number.isInteger(ui.picture_slots)
    ? ui.picture_slots
    : 5;
  const modeDefinitions = (isSide) => {
    const source =
      ui[isSide ? "side_modes" : "light_modes"] ||
      catalog[isSide ? "side_modes" : "light_modes"] ||
      {};
    return Object.fromEntries(
      Object.entries(source).map(([name, definition]) => [
        name,
        typeof definition === "object"
          ? definition
          : {
              code: definition,
              speed_max: isSide ? 3 : 4,
              option_max: name === "picture" ? pictureSlots - 1 : 15,
              rgb: true,
              rainbow: true,
              brightness: true,
            },
      ]),
    );
  };
  const modes = modeDefinitions(side);
  const definition = modes[value?.mode] || modes[Object.keys(modes)[0]] || {};
  const supports = (field) => definition[field] !== false;
  const maxFor = (field, fallback) =>
    Number.isInteger(definition[field]) ? definition[field] : fallback;
  const sanitize = (mode, source) => {
    const metadata = modeDefinitions(side)[mode] || {};
    const speedMax = Number.isInteger(metadata.speed_max)
      ? metadata.speed_max
      : side
        ? 3
        : 4;
    const optionMax = Number.isInteger(metadata.option_max)
      ? metadata.option_max
      : 15;
    return {
      ...source,
      mode,
      rgb: metadata.rgb === false ? 0xffffff : source.rgb,
      rainbow: metadata.rainbow === false ? false : source.rainbow,
      speed:
        metadata.speed_max === false ? 0 : Math.min(source.speed, speedMax),
      option:
        metadata.option_max === false ? 0 : Math.min(source.option, optionMax),
      brightness: metadata.brightness === false ? 4 : source.brightness,
    };
  };
  useEffect(() => {
    if (connected)
      run(async () => setLights(await api("read", { section: "lighting" })));
  }, [connected, epoch]);
  function update(field, v) {
    setLights({ ...lights, [key]: { ...value, [field]: v } });
  }
  if (!value) return null;
  return (
    <>
      <div className="toolbar segments">
        {["Main lighting", "Side lighting"].map(
          (name, i) =>
            (!i || hasSide) && (
              <button
                key={name}
                aria-pressed={side === Boolean(i)}
                onClick={() => setSide(Boolean(i))}
              >
                {name}
              </button>
            ),
        )}
      </div>
      <Panel title="Lighting effect">
        <div className="fields">
          <Field label="Effect">
            <Select
              value={value.mode}
              options={Object.keys(modes).map((k) => [k, titleCase(k)])}
              onChange={(e) =>
                setLights({
                  ...lights,
                  [key]: sanitize(e.target.value, value),
                })
              }
            />
          </Field>
          {supports("rgb") && (
            <Field label="Color">
              <input
                type="color"
                value={`#${value.rgb.toString(16).padStart(6, "0")}`}
                onChange={(e) =>
                  update("rgb", parseInt(e.target.value.slice(1), 16))
                }
              />
            </Field>
          )}
          {supports("brightness") && (
            <Field label={`Brightness · ${value.brightness}`}>
              <input
                type="range"
                min="0"
                max={maxFor("brightness_max", 4)}
                value={value.brightness}
                onChange={(e) => update("brightness", Number(e.target.value))}
              />
            </Field>
          )}
          {definition.speed_max !== false && (
            <Field label={`Speed · ${value.speed}`}>
              <input
                type="range"
                min="0"
                max={maxFor("speed_max", side ? 3 : 4)}
                value={value.speed}
                onChange={(e) => update("speed", Number(e.target.value))}
              />
            </Field>
          )}
          {definition.option_max !== false && (
            <Field label="Effect option">
              <input
                type="number"
                min="0"
                max={maxFor(
                  "option_max",
                  value.mode === "picture" ? pictureSlots - 1 : 15,
                )}
                value={value.option}
                onChange={(e) => update("option", Number(e.target.value))}
              />
            </Field>
          )}
          {supports("rainbow") && (
            <label className="check">
              <input
                type="checkbox"
                checked={value.rainbow}
                onChange={(e) => update("rainbow", e.target.checked)}
              />
              Rainbow
            </label>
          )}
        </div>
        <div className="apply-row">
          <Button
            primary
            disabled={!connected || busy}
            onClick={() =>
              run(async () => {
                const result = await api("write", {
                  kind: "lighting",
                  side,
                  ...value,
                });
                setLights({ ...lights, [key]: result });
              }, "Lighting read back from keyboard.")
            }
          >
            Apply lighting
          </Button>
        </div>
      </Panel>
      <Panel title="Custom colors">
        <div className="fields">
          <Field label="Pattern">
            <Select
              value={index}
              options={Array.from({ length: pictureSlots }, (_, i) => [
                i,
                `Pattern ${i + 1}`,
              ])}
              onChange={(e) => {
                setIndex(Number(e.target.value));
                setColors(null);
              }}
            />
          </Field>
          <Field label="Paint color">
            <input
              type="color"
              value={brush}
              onChange={(e) => setBrush(e.target.value)}
            />
          </Field>
          <Button
            disabled={!connected || busy}
            onClick={() =>
              run(async () => {
                const value = await api("read", { section: "picture", index });
                const hex = value.colors || "";
                setColors(
                  Array.from({ length: Math.floor(hex.length / 6) }, (_, i) =>
                    hex.slice(i * 6, i * 6 + 6),
                  ),
                );
              })
            }
          >
            Load pattern
          </Button>
        </div>
        <p className="muted">
          Load a pattern, then paint its physical color slots.
        </p>
        {colors && (
          <div className="color-grid">
            {colors.map((color, i) => (
              <button
                key={i}
                title={`Color slot ${i}`}
                aria-label={`Color slot ${i}`}
                style={{ background: `#${color}` }}
                onClick={() =>
                  setColors(
                    colors.map((c, j) => (i === j ? brush.slice(1) : c)),
                  )
                }
              />
            ))}
          </div>
        )}
        <Button
          disabled={!connected || busy || !colors}
          onClick={() =>
            run(
              () =>
                api("write", {
                  kind: "picture",
                  index,
                  colors: colors.join(""),
                }),
              "Pattern verified.",
            )
          }
        >
          Save pattern
        </Button>
      </Panel>
    </>
  );
}
