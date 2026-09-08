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
export default function Lighting({ catalog, connected, busy, run, epoch }) {
  const [side, setSide] = useState(false),
    [lights, setLights] = useState({ main: initial, side: initial });
  const [index, setIndex] = useState(0),
    [colors, setColors] = useState(null),
    [brush, setBrush] = useState("#365df5");
  useEffect(() => {
    if (connected)
      run(async () => setLights(await api("read", { section: "lighting" })));
  }, [connected, epoch]);
  const key = side ? "side" : "main",
    value = lights[key];
  function update(field, v) {
    setLights({ ...lights, [key]: { ...value, [field]: v } });
  }
  return (
    <>
      <div className="toolbar segments">
        {["Main lighting", "Side lighting"].map((name, i) => (
          <button
            key={name}
            aria-pressed={side === Boolean(i)}
            onClick={() => setSide(Boolean(i))}
          >
            {name}
          </button>
        ))}
      </div>
      <Panel title="Lighting effect">
        <div className="fields">
          <Field label="Effect">
            <Select
              value={value.mode}
              options={Object.keys(
                side ? catalog.side_modes : catalog.light_modes,
              ).map((k) => [k, titleCase(k)])}
              onChange={(e) => update("mode", e.target.value)}
            />
          </Field>
          <Field label="Color">
            <input
              type="color"
              value={`#${value.rgb.toString(16).padStart(6, "0")}`}
              onChange={(e) =>
                update("rgb", parseInt(e.target.value.slice(1), 16))
              }
            />
          </Field>
          <Field label={`Brightness · ${value.brightness}`}>
            <input
              type="range"
              min="0"
              max="4"
              value={value.brightness}
              onChange={(e) => update("brightness", Number(e.target.value))}
            />
          </Field>
          <Field label={`Speed · ${value.speed}`}>
            <input
              type="range"
              min="0"
              max={side ? "3" : "4"}
              value={value.speed}
              onChange={(e) => update("speed", Number(e.target.value))}
            />
          </Field>
          <Field label="Effect option">
            <input
              type="number"
              min="0"
              max={value.mode === "picture" ? "4" : "15"}
              value={value.option}
              onChange={(e) => update("option", Number(e.target.value))}
            />
          </Field>
          <label className="check">
            <input
              type="checkbox"
              checked={value.rainbow}
              onChange={(e) => update("rainbow", e.target.checked)}
            />
            Rainbow
          </label>
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
              options={[0, 1, 2, 3, 4].map((i) => [i, `Pattern ${i + 1}`])}
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
                setColors(value.colors.match(/.{6}/g));
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
