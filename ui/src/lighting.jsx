import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select, titleCase } from "./controls";
import CustomPattern from "./custom-pattern";
const initial = {
  mode: "solid",
  rgb: 0xffffff,
  brightness: 4,
  speed: 0,
  option: 0,
  rainbow: false,
};

// docs/glyph-protocol.md: LightList order is not the wire mode order. Keep
// this mapping explicit so catalog metadata cannot accidentally shift IDs.
const EFFECTS = {
  LightOff: ["off", "Off"],
  LightAlwaysOn: ["solid", "Solid"],
  LightBreath: ["breathing", "Breathing"],
  LightNeon: ["neon", "Neon"],
  LightWave: ["wave", "Wave"],
  LightRipple: ["ripple", "Ripple"],
  LightRaindrop: ["raindrop", "Raindrop"],
  LightSnake: ["snake", "Snake"],
  LightPressAction: ["reactive", "Reactive"],
  LightConverage: ["convergence", "Convergence"],
  LightSineWave: ["sine", "Sine wave"],
  LightKaleidoscope: ["kaleidoscope", "Kaleidoscope"],
  LightLineWave: ["line-wave", "Line wave"],
  LightUserPicture: ["picture", "User picture"],
  LightLaser: ["laser", "Laser"],
  LightCircleWave: ["circle-wave", "Circle wave"],
  LightDazzing: ["dazzling", "Dazzling"],
  LightRainDown: ["rain", "Rain"],
  LightMeteor: ["meteor", "Meteor"],
  LightPressActionOff: ["reactive-off", "Reactive off"],
  LightScreenColor: ["screen", "Screen color"],
  LightMusicFollow2: ["music", "Music follow"],
};
const OPTION_LABELS = {
  向右: "Right",
  向左: "Left",
  向下: "Down",
  向上: "Up",
  Z字形: "Z shape",
  回形: "Loop",
  向外: "Outward",
  向内: "Inward",
  逆时针: "Counter-clockwise",
  顺时针: "Clockwise",
  图案1: "Pattern 1",
  图案2: "Pattern 2",
  图案3: "Pattern 3",
  图案4: "Pattern 4",
  图案5: "Pattern 5",
  upright: "Upright",
  separate: "Separate",
  intersect: "Intersect",
};
function effectMetadata(catalog, side, mode) {
  const section = catalog.lighting_capabilities?.[side ? "side" : "main"];
  const type = section?.types?.find((item) => EFFECTS[item.type]?.[0] === mode);
  return type || null;
}
function effectOptions(catalog, side, mode) {
  const metadata = effectMetadata(catalog, side, mode);
  return metadata?.options || [];
}
function labelOption(option) {
  return OPTION_LABELS[option] || option;
}
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
  const metadata = effectMetadata(catalog, side, value.mode);
  const options = effectOptions(catalog, side, value.mode);
  const modes = Object.keys(side ? catalog.side_modes : catalog.light_modes)
    .map((mode) => [
      mode,
      Object.values(EFFECTS).find(([name]) => name === mode)?.[1] ||
        titleCase(mode),
    ])
    .filter(([mode]) => effectMetadata(catalog, side, mode));
  const knownMode = Boolean(metadata);
  if (!knownMode)
    modes.push([value.mode, `Unknown effect ID ${value.mode_id ?? ""}`]);
  function update(field, v) {
    setLights({ ...lights, [key]: { ...value, [field]: v } });
  }
  function changeMode(mode) {
    // Reset fields that belong to the previous effect. This prevents a hidden
    // option/rainbow value from being sent when the user changes effects.
    const next = effectMetadata(catalog, side, mode);
    const previous = metadata;
    setLights({
      ...lights,
      [key]: {
        ...value,
        mode,
        option: 0,
        speed:
          next?.maxSpeed == null
            ? 0
            : previous?.maxSpeed == null
              ? next.maxSpeed
              : Math.min(value.speed, next.maxSpeed),
        brightness:
          next?.maxValue == null
            ? 0
            : previous?.maxValue == null
              ? next.maxValue
              : Math.min(value.brightness, next.maxValue),
        rgb: next?.rgb ? value.rgb : 0xffffff,
        rainbow: Boolean(next?.dazzle) && value.rainbow,
      },
    });
  }
  const canOption = Boolean(metadata?.options?.length);
  const canSpeed = metadata?.maxSpeed != null;
  const canBrightness = metadata?.maxValue != null;
  const canRgb = Boolean(metadata?.rgb);
  const canRainbow = Boolean(metadata?.dazzle);
  return (
    <>
      <div className="toolbar segments">
        {["Main lighting", "Side lighting"].map((name, i) => (
          <button
            key={name}
            aria-pressed={side === Boolean(i)}
            disabled={busy}
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
              options={modes}
              disabled={busy}
              onChange={(e) => changeMode(e.target.value)}
            />
          </Field>
          {canRgb && (
            <Field label="Color">
              <input
                type="color"
                value={`#${value.rgb.toString(16).padStart(6, "0")}`}
                disabled={busy}
                onChange={(e) =>
                  update("rgb", parseInt(e.target.value.slice(1), 16))
                }
              />
            </Field>
          )}
          {canBrightness && (
            <Field label={`Brightness · ${value.brightness}`}>
              <input
                type="range"
                min="0"
                max={metadata.maxValue}
                value={value.brightness}
                disabled={busy}
                onChange={(e) => update("brightness", Number(e.target.value))}
              />
            </Field>
          )}
          {canSpeed && (
            <Field label={`Speed · ${value.speed}`}>
              <input
                type="range"
                min="0"
                max={metadata.maxSpeed}
                value={value.speed}
                disabled={busy}
                onChange={(e) => update("speed", Number(e.target.value))}
              />
            </Field>
          )}
          {canOption && (
            <Field label="Effect option">
              <Select
                value={value.option}
                options={options.map((option, i) => [i, labelOption(option)])}
                disabled={busy}
                onChange={(e) => update("option", Number(e.target.value))}
              />
            </Field>
          )}
          {canRainbow && (
            <label className="check">
              <input
                type="checkbox"
                checked={value.rainbow}
                disabled={busy}
                onChange={(e) => update("rainbow", e.target.checked)}
              />
              Rainbow
            </label>
          )}
        </div>
        {(value.mode === "music" || value.mode === "screen") && (
          <p className="muted">
            {value.mode === "music"
              ? "Music-follow input is not provided by this host yet."
              : "Screen-color input is not provided by this host yet."}
          </p>
        )}
        <div className="apply-row">
          <Button
            primary
            disabled={!connected || busy || !knownMode}
            onClick={() =>
              run(async () => {
                const result = await api("write", {
                  kind: "lighting",
                  side,
                  ...value,
                  rgb: canRgb ? value.rgb : 0xffffff,
                  brightness: canBrightness ? value.brightness : 0,
                  speed: canSpeed ? value.speed : 0,
                  option: canOption ? value.option : 0,
                  rainbow: canRainbow ? value.rainbow : false,
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
        <CustomPattern
          index={index}
          setIndex={setIndex}
          colors={colors}
          setColors={setColors}
          brush={brush}
          setBrush={setBrush}
          connected={connected}
          busy={busy}
          run={run}
        />
      </Panel>
    </>
  );
}
