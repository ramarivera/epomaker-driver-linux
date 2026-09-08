import React, { useEffect, useMemo, useState } from "react";
import { Volume1, Volume2, Play } from "lucide-react";
import { api } from "./api";
import { Button, Field, Panel, Select, titleCase } from "./controls";
const DOM = {
  Backspace: 42,
  Tab: 43,
  CapsLock: 57,
  Enter: 40,
  ShiftLeft: 225,
  ShiftRight: 229,
  ControlLeft: 224,
  MetaLeft: 227,
  AltLeft: 226,
  Space: 44,
  AltRight: 230,
  Backslash: 49,
  Escape: 41,
  Backquote: 53,
  Minus: 45,
  Equal: 46,
  BracketLeft: 47,
  BracketRight: 48,
  Semicolon: 51,
  Quote: 52,
  ArrowLeft: 80,
  ArrowDown: 81,
  ArrowUp: 82,
  PageUp: 75,
  PageDown: 78,
  ArrowRight: 79,
  Comma: 54,
  Period: 55,
  Slash: 56,
  PrintScreen: 70,
  End: 77,
  Insert: 73,
  Home: 74,
  Delete: 76,
};
for (let i = 0; i < 26; i++) DOM[`Key${String.fromCharCode(65 + i)}`] = i + 4;
for (let i = 1; i <= 9; i++) DOM[`Digit${i}`] = i + 29;
DOM.Digit0 = 39;
for (let i = 1; i <= 12; i++) DOM[`F${i}`] = 57 + i;
const SPECIAL = {
  Fn: [10, 1, 0, 0],
  AudioVolumeDown: [3, 0, 234, 0],
  AudioVolumeUp: [3, 0, 233, 0],
  MediaPlayPause: [3, 0, 205, 0],
};
const hex = (values) =>
  values.map((n) => n.toString(16).padStart(2, "0")).join("");
function decode(raw, catalog) {
  if (raw.every((n) => n === 0)) return { type: "Disabled" };
  if (raw[0] === 0)
    return { type: "Keyboard", key: raw[2], second: raw[3], modifiers: raw[1] };
  if (raw[0] === 9 && raw[1] <= 2 && raw[3] === 0)
    return { type: "Macro", key: raw[2], mode: raw[1] };
  for (const [type, values, opcode] of [
    ["Media", catalog.media, 3],
    ["Mouse", catalog.mouse, 1],
  ]) {
    const name = Object.keys(values).find(
      (k) => values[k] === raw[2] + raw[3] * 256,
    );
    if (raw[0] === opcode && raw[1] === 0 && name) return { type, key: name };
  }
  return { type: "Raw", key: hex(raw) };
}
export default function Keymap({ catalog, connected, busy, run, epoch }) {
  const [profile, setProfile] = useState(0),
    [layer, setLayer] = useState("Main"),
    [matrix, setMatrix] = useState(catalog.matrices[0]);
  const [slot, setSlot] = useState(0),
    [draft, setDraft] = useState({
      type: "Keyboard",
      key: 4,
      modifiers: 0,
      second: 0,
    });
  const target = {
    profile: layer === "Main" ? profile : 0,
    fn: layer !== "Main",
    os_mode: layer === "Fn Mac" ? 1 : 0,
  };
  const keys = useMemo(
    () =>
      Object.entries(catalog.layout.layout).map(([name, geometry]) => {
        const action = SPECIAL[name] || [0, 0, DOM[name], 0];
        const slot = Array.from({ length: 128 }, (_, i) => i).find((i) =>
          action.every((n, j) => catalog.matrices[0][i * 4 + j] === n),
        );
        return { name, geometry, slot };
      }),
    [catalog],
  );
  useEffect(() => {
    setSlot(keys.find((k) => k.name === "KeyA").slot);
  }, [keys]);
  useEffect(() => {
    if (connected)
      run(async () =>
        setMatrix((await api("read", { section: "keymap", ...target })).raw),
      );
    else
      setMatrix(
        catalog.matrices[layer === "Main" ? 0 : layer === "Fn Windows" ? 1 : 2],
      );
  }, [connected, epoch, profile, layer]);
  useEffect(() => {
    setDraft(decode(matrix.slice(slot * 4, slot * 4 + 4), catalog));
  }, [matrix, slot, catalog]);
  const current = decode(matrix.slice(slot * 4, slot * 4 + 4), catalog);
  const nameFor = (action) =>
    action.type === "Keyboard"
      ? (
          Object.keys(catalog.keys).find(
            (k) => catalog.keys[k] === action.key,
          ) || `Usage ${action.key}`
        ).toUpperCase()
      : action.type === "Disabled"
        ? "Disabled"
        : action.type === "Macro"
          ? `Macro ${action.key}`
          : String(action.key);
  function actionBytes() {
    if (draft.type === "Keyboard")
      return hex([
        0,
        Number(draft.modifiers || 0),
        Number(draft.key),
        Number(draft.second || 0),
      ]);
    if (draft.type === "Disabled") return "00000000";
    if (draft.type === "Macro")
      return hex([9, Number(draft.mode || 0), Number(draft.key), 0]);
    if (draft.type === "Raw") return draft.key;
    const n = (draft.type === "Media" ? catalog.media : catalog.mouse)[
      draft.key
    ];
    return hex([draft.type === "Media" ? 3 : 1, 0, n & 255, n >> 8]);
  }
  function changeType(type) {
    setDraft({
      type,
      key:
        type === "Keyboard"
          ? 4
          : type === "Media"
            ? "play-pause"
            : type === "Mouse"
              ? "left"
              : type === "Raw"
                ? hex(matrix.slice(slot * 4, slot * 4 + 4))
                : 0,
      modifiers: 0,
      second: 0,
      mode: 0,
    });
  }
  return (
    <>
      <div className="toolbar">
        <Select
          aria-label="Profile"
          value={profile}
          onChange={(e) => setProfile(Number(e.target.value))}
          disabled={busy || layer !== "Main"}
          options={[0, 1, 2].map((i) => [i, `Profile ${i + 1}`])}
        />
        <div className="segments">
          {["Main", "Fn Windows", "Fn Mac"].map((name) => (
            <button
              key={name}
              disabled={busy}
              aria-pressed={layer === name}
              onClick={() => setLayer(name)}
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      <div className="keyboard-scroll">
        <div
          className="keyboard"
          style={{
            aspectRatio: `${catalog.layout.width + 20}/${catalog.layout.height + 20}`,
          }}
        >
          {keys.map(({ name, geometry: g, slot: keySlot }) => {
            const Icon =
              name === "AudioVolumeDown"
                ? Volume1
                : name === "AudioVolumeUp"
                  ? Volume2
                  : Play;
            return (
              <button
                key={name}
                aria-label={`Key ${g.displayText?.join(" ") || name}`}
                title={`${name} · slot ${keySlot}`}
                disabled={busy || keySlot === undefined}
                aria-pressed={slot === keySlot}
                onClick={() => setSlot(keySlot)}
                className={`key ${slot === keySlot ? "selected" : ""} ${g.type === "knob" ? "knob" : ""}`}
                style={{
                  left: `${((g.x + 10) / (catalog.layout.width + 20)) * 100}%`,
                  top: `${((g.y + 10) / (catalog.layout.height + 20)) * 100}%`,
                  width: `${(g.width / (catalog.layout.width + 20)) * 100}%`,
                  height: `${(g.height / (catalog.layout.height + 20)) * 100}%`,
                }}
              >
                {g.type === "knob" ? (
                  <Icon size={18} />
                ) : (
                  g.displayText?.join("\n") || name
                )}
              </button>
            );
          })}
        </div>
      </div>
      <div className="assignment-grid">
        <Panel title="Key assignment">
          <div className="fields">
            <Field label="Action">
              <Select
                value={draft.type}
                onChange={(e) => changeType(e.target.value)}
                options={[
                  "Keyboard",
                  "Media",
                  "Mouse",
                  "Macro",
                  "Disabled",
                  "Raw",
                ]}
              />
            </Field>
            {draft.type === "Keyboard" && (
              <>
                <Field label="Key">
                  <Select
                    value={draft.key}
                    onChange={(e) =>
                      setDraft({ ...draft, key: Number(e.target.value) })
                    }
                    options={Object.entries(catalog.keys).map(([k, v]) => [
                      v,
                      k.toUpperCase(),
                    ])}
                  />
                </Field>
                <Field label="Modifiers">
                  <div className="checks">
                    {["ctrl", "shift", "alt", "meta"].map((name) => (
                      <label key={name}>
                        <input
                          type="checkbox"
                          checked={Boolean(
                            (draft.modifiers || 0) & catalog.modifiers[name],
                          )}
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              modifiers: e.target.checked
                                ? (draft.modifiers || 0) |
                                  catalog.modifiers[name]
                                : (draft.modifiers || 0) &
                                  ~catalog.modifiers[name],
                            })
                          }
                        />
                        {titleCase(name)}
                      </label>
                    ))}
                  </div>
                </Field>
              </>
            )}
            {["Media", "Mouse"].includes(draft.type) && (
              <Field label="Assignment">
                <Select
                  value={draft.key}
                  onChange={(e) => setDraft({ ...draft, key: e.target.value })}
                  options={Object.keys(
                    draft.type === "Media" ? catalog.media : catalog.mouse,
                  ).map((k) => [k, titleCase(k)])}
                />
              </Field>
            )}
            {draft.type === "Macro" && (
              <>
                <Field label="Macro slot">
                  <input
                    type="number"
                    min="0"
                    max="255"
                    value={draft.key}
                    onChange={(e) =>
                      setDraft({ ...draft, key: Number(e.target.value) })
                    }
                  />
                </Field>
                <Field label="Playback">
                  <Select
                    value={draft.mode || 0}
                    onChange={(e) =>
                      setDraft({ ...draft, mode: Number(e.target.value) })
                    }
                    options={Object.entries(catalog.macro_modes).map(
                      ([k, v]) => [v, titleCase(k)],
                    )}
                  />
                </Field>
              </>
            )}
            {draft.type === "Raw" && (
              <Field label="Four-byte action">
                <input
                  value={draft.key}
                  onChange={(e) => setDraft({ ...draft, key: e.target.value })}
                />
              </Field>
            )}
          </div>
        </Panel>
        <Panel title="Current assignment">
          <div className="current-assignment">{nameFor(current)}</div>
          <p className="muted">Changes apply to the selected profile.</p>
        </Panel>
      </div>
      <div className="apply-row">
        <Button
          primary
          disabled={!connected || busy}
          onClick={() =>
            run(async () => {
              await api("write", {
                kind: "key",
                slot,
                action: actionBytes(),
                ...target,
              });
              setMatrix(
                (await api("read", { section: "keymap", ...target })).raw,
              );
            }, "Assignment verified.")
          }
        >
          Apply to keyboard
        </Button>
        <span className="muted">
          {connected
            ? "Writes are checked against the keyboard."
            : "Connect a keyboard to apply changes."}
        </span>
      </div>
    </>
  );
}
