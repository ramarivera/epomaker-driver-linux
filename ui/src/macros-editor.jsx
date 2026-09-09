import React, { useState } from "react";
import { ArrowUp, ArrowDown, Trash2 } from "lucide-react";
import { api, download } from "./api";
import { Button, Field, Panel, Select, titleCase } from "./controls";
import MacroRecorder from "./macro-recorder";
const makeEvent = (type) =>
  type === "mouse_move"
    ? { type, dx: 0, dy: 0, delay_ms: 10 }
    : type === "mouse_button"
      ? { type, button: "left", down: true, delay_ms: 10 }
      : { hid_usage: 4, down: true, delay_ms: 10 };
export default function MacrosEditor({ connected, busy, run }) {
  const [recorderValidating, setRecorderValidating] = useState(false);
  const [slot, setSlot] = useState(0),
    [value, setValue] = useState({ repeat: 1, events: [] }),
    [kind, setKind] = useState("keyboard"),
    [raw, setRaw] = useState(null),
    [warning, setWarning] = useState("");
  const setEvent = (i, field, v) =>
    setValue({
      ...value,
      events: value.events.map((e, j) => (i === j ? { ...e, [field]: v } : e)),
    });
  function move(i, delta) {
    const events = [...value.events];
    [events[i], events[i + delta]] = [events[i + delta], events[i]];
    setValue({ ...value, events });
  }
  return (
    <Panel title="Macro sequence">
      <div className="fields">
        <Field label="Macro slot">
          <input
            type="number"
            min="0"
            max="255"
            value={slot}
            onChange={(e) => setSlot(Number(e.target.value))}
          />
        </Field>
        <Button
          disabled={!connected || busy || recorderValidating}
          onClick={() =>
            run(async () => {
              const result = await api("read", { section: "macro", slot });
              setValue(result.decoded || null);
              setRaw(result.data);
              setWarning(result.decode_error || "");
            })
          }
        >
          Load macro
        </Button>
        <Button
          disabled={busy || recorderValidating}
          onClick={() => {
            setValue({ repeat: 1, events: [] });
            setWarning("");
            setRaw(null);
          }}
        >
          New macro
        </Button>
        <Field label="Import JSON">
          <input
            type="file"
            accept=".json"
            disabled={busy || recorderValidating}
            onChange={(e) => {
              const file = e.target.files[0];
              if (file)
                run(async () => {
                  const v = JSON.parse(await file.text());
                  const valid = await api("validate_macro", { value: v });
                  setValue(valid);
                  setRaw(null);
                  setWarning("");
                });
            }}
          />
        </Field>
      </div>
      {warning && (
        <p role="alert" className="error">
          {warning}
        </p>
      )}
      {raw && (
        <Button
          onClick={() =>
            download(`macro-${slot}-raw.json`, { slot, data: raw })
          }
        >
          Export raw data
        </Button>
      )}
      {value && (
        <>
          <MacroRecorder
            busy={busy}
            onValidatingChange={setRecorderValidating}
            onUse={(recorded) => {
              setValue(recorded);
              setRaw(null);
              setWarning("");
            }}
          />
          <div className="fields">
            <Field label="Repeat count">
              <input
                type="number"
                min="0"
                max="65535"
                value={value.repeat}
                onChange={(e) =>
                  setValue({ ...value, repeat: Number(e.target.value) })
                }
              />
            </Field>
            <Field label="New event">
              <Select
                value={kind}
                options={["keyboard", "mouse_button", "mouse_move"].map((k) => [
                  k,
                  titleCase(k.replaceAll("_", "-")),
                ])}
                onChange={(e) => setKind(e.target.value)}
              />
            </Field>
            <Button
              onClick={() =>
                setValue({
                  ...value,
                  events: [...value.events, makeEvent(kind)],
                })
              }
            >
              Add event
            </Button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Action</th>
                  <th>Delay (ms)</th>
                  <th>Order</th>
                </tr>
              </thead>
              <tbody>
                {value.events.map((event, i) => {
                  const type = event.type || "keyboard";
                  return (
                    <tr key={i}>
                      <td>{titleCase(type.replaceAll("_", "-"))}</td>
                      <td>
                        {type === "mouse_move" ? (
                          <div className="fields compact">
                            <input
                              aria-label={`Event ${i + 1} X movement`}
                              type="number"
                              min="-128"
                              max="127"
                              value={event.dx}
                              onChange={(e) =>
                                setEvent(i, "dx", Number(e.target.value))
                              }
                            />
                            <input
                              aria-label={`Event ${i + 1} Y movement`}
                              type="number"
                              min="-128"
                              max="127"
                              value={event.dy}
                              onChange={(e) =>
                                setEvent(i, "dy", Number(e.target.value))
                              }
                            />
                          </div>
                        ) : (
                          <div className="fields compact">
                            {type === "keyboard" ? (
                              <input
                                aria-label={`Event ${i + 1} key usage`}
                                type="number"
                                min="4"
                                max="239"
                                value={event.hid_usage}
                                onChange={(e) =>
                                  setEvent(
                                    i,
                                    "hid_usage",
                                    Number(e.target.value),
                                  )
                                }
                              />
                            ) : (
                              <Select
                                aria-label={`Event ${i + 1} mouse button`}
                                value={event.button}
                                options={[
                                  "left",
                                  "right",
                                  "middle",
                                  "back",
                                  "forward",
                                ]}
                                onChange={(e) =>
                                  setEvent(i, "button", e.target.value)
                                }
                              />
                            )}
                            <Select
                              aria-label={`Event ${i + 1} direction`}
                              value={String(event.down)}
                              options={[
                                ["true", "Press"],
                                ["false", "Release"],
                              ]}
                              onChange={(e) =>
                                setEvent(i, "down", e.target.value === "true")
                              }
                            />
                          </div>
                        )}
                      </td>
                      <td>
                        <input
                          aria-label={`Event ${i + 1} delay`}
                          type="number"
                          min="1"
                          max="65535"
                          value={event.delay_ms}
                          onChange={(e) =>
                            setEvent(i, "delay_ms", Number(e.target.value))
                          }
                        />
                      </td>
                      <td className="row-actions">
                        <button
                          title="Move up"
                          aria-label={`Move event ${i + 1} up`}
                          disabled={i === 0}
                          onClick={() => move(i, -1)}
                        >
                          <ArrowUp size={16} />
                        </button>
                        <button
                          title="Move down"
                          aria-label={`Move event ${i + 1} down`}
                          disabled={i === value.events.length - 1}
                          onClick={() => move(i, 1)}
                        >
                          <ArrowDown size={16} />
                        </button>
                        <button
                          title="Remove event"
                          aria-label={`Remove event ${i + 1}`}
                          onClick={() =>
                            setValue({
                              ...value,
                              events: value.events.filter((_, j) => i !== j),
                            })
                          }
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!value.events.length && (
            <p className="muted">
              Add keyboard or mouse events to create a sequence.
            </p>
          )}
          <div className="apply-row">
            <Button
              primary
              disabled={!connected || busy || recorderValidating}
              onClick={() =>
                run(
                  () => api("write", { kind: "macro", slot, value }),
                  "Macro readback verified.",
                )
              }
            >
              Save macro
            </Button>
            <Button onClick={() => download(`macro-${slot}.json`, value)}>
              Export JSON
            </Button>
            <span className="muted">Assign this slot to a key in Keymap.</span>
          </div>
        </>
      )}
    </Panel>
  );
}
