import React, { useMemo } from "react";
import { Play, Volume1, Volume2 } from "lucide-react";
import { layoutKeys } from "./keyboard-layout";

const KNOB_ICONS = {
  AudioVolumeDown: Volume1,
  AudioVolumeUp: Volume2,
  MediaPlayPause: Play,
};
const readableName = (name, geometry) => {
  const display = geometry.displayText?.join(" ") || name;
  const side = name.match(/(Left|Right)$/)?.[1];
  return side && geometry.displayText ? `${display} ${side}` : display;
};
const contrast = (hex) => {
  const value = Number.parseInt(hex || "000000", 16);
  const luminance =
    (0.299 * (value >> 16) +
      0.587 * ((value >> 8) & 255) +
      0.114 * (value & 255)) /
    255;
  return luminance > 0.55 ? "#111827" : "#ffffff";
};

export default function PatternKeyboard({
  catalog,
  colors,
  onPaint,
  disabled = false,
}) {
  const keys = useMemo(() => layoutKeys(catalog), [catalog]);
  const denominator = catalog.layout.width + 20;
  const height = catalog.layout.height + 20;
  return (
    <div className="pattern-keyboard-scroll">
      <div
        className="pattern-keyboard"
        style={{ aspectRatio: `${denominator}/${height}` }}
      >
        {keys.map(({ name, geometry, slot }) => {
          const label = readableName(name, geometry);
          const usable =
            Number.isInteger(slot) &&
            slot >= 0 &&
            slot < 126 &&
            Boolean(colors?.[slot]);
          const Icon =
            geometry.type === "knob" ? KNOB_ICONS[name] || Play : null;
          const color = usable ? colors[slot] : "d7dee8";
          return (
            <button
              key={name}
              type="button"
              className={`pattern-key${geometry.type === "knob" ? " knob" : ""}`}
              disabled={disabled || !usable}
              aria-label={`Paint key ${label}`}
              title={`${label} · RGB slot ${usable ? slot : "unmapped"}`}
              style={{
                left: `${((geometry.x + 10) / denominator) * 100}%`,
                top: `${((geometry.y + 10) / height) * 100}%`,
                width: `${(geometry.width / denominator) * 100}%`,
                height: `${(geometry.height / height) * 100}%`,
                background: `#${color}`,
                color: contrast(color),
              }}
              onClick={() => usable && onPaint(slot)}
            >
              {Icon ? <Icon size={18} aria-hidden="true" /> : label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
