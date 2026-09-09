import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";
export default function Settings({ connected, transport, busy, run, epoch }) {
  const [value, setValue] = useState(null);
  const load = async () => setValue(await api("read", { section: "settings" }));
  useEffect(() => {
    if (connected) run(load);
    else setValue(null);
  }, [connected, epoch]);
  if (!value)
    return (
      <Panel title="Keyboard settings">
        <p className="muted">
          Connect a keyboard to read its current settings.
        </p>
      </Panel>
    );
  const write = (data, message) =>
    run(async () => {
      await api("write", data);
      await load();
    }, message);
  return (
    <>
      <Panel title="Device identity and firmware">
        <p>
          Model: {value.model || "Epomaker Glyph"} · Internal ID:{" "}
          {value.identity?.device_id ?? "Unknown"}
        </p>
        <p>
          Connected transport:{" "}
          {transport === "usb"
            ? "Wired USB"
            : transport === "bluetooth"
              ? "Bluetooth"
              : "Unknown"}
        </p>
        <p>
          USB firmware code:{" "}
          {value.identity?.usb_version
            ? `${value.identity.usb_version} (0x${value.identity.usb_version.toString(16).padStart(4, "0")})`
            : "Unavailable"}
        </p>
        <p className="muted">
          Firmware identity was read when connecting. Reconnect to refresh it
          after a firmware change. This is the raw USB firmware code; other
          component versions and firmware updates are not yet available here.
        </p>
      </Panel>
      <div className="two-columns">
        <Panel title="Profile and response">
          <div className="fields">
            <Field label="Active profile">
              <Select
                value={value.profile}
                options={[0, 1, 2].map((i) => [i, `Profile ${i + 1}`])}
                onChange={(e) =>
                  setValue({ ...value, profile: Number(e.target.value) })
                }
              />
            </Field>
            <Button
              disabled={busy}
              onClick={() =>
                write(
                  { kind: "profile", profile: value.profile },
                  "Profile verified.",
                )
              }
            >
              Set profile
            </Button>
          </div>
          {value.identity?.device_id !== 3059 && (
            <div className="fields">
              <Field label="Debounce (ms)">
                <input
                  type="number"
                  min="0"
                  max="255"
                  value={value.debounce}
                  onChange={(e) =>
                    setValue({ ...value, debounce: Number(e.target.value) })
                  }
                />
              </Field>
              <Button
                disabled={busy}
                onClick={() =>
                  write(
                    { kind: "debounce", milliseconds: value.debounce },
                    "Debounce verified.",
                  )
                }
              >
                Set debounce
              </Button>
            </div>
          )}
          <p className="muted">
            Reported polling rate: {value.report_rate ?? "Unknown"} Hz
          </p>
        </Panel>
        <Panel title="Operating system">
          <div className="fields">
            <Field label="System layer">
              <Select
                value={value.options.system}
                options={[
                  ["win", "Windows"],
                  ["mac", "Mac"],
                ]}
                onChange={(e) =>
                  setValue({
                    ...value,
                    options: { ...value.options, system: e.target.value },
                  })
                }
              />
            </Field>
            <label className="check">
              <input
                type="checkbox"
                checked={value.options.wasd_swap}
                onChange={(e) =>
                  setValue({
                    ...value,
                    options: { ...value.options, wasd_swap: e.target.checked },
                  })
                }
              />
              Swap WASD and arrows
            </label>
          </div>
          <Button
            disabled={busy}
            onClick={() =>
              write(
                {
                  kind: "options",
                  system: value.options.system,
                  wasd_swap: value.options.wasd_swap,
                },
                "OS options verified.",
              )
            }
          >
            Apply OS options
          </Button>
          <div className="fields">
            <Field label="Automatic OS selection">
              <Select
                value={String(value.auto_os)}
                options={[
                  ["true", "On"],
                  ["false", "Off"],
                ]}
                onChange={(e) =>
                  setValue({ ...value, auto_os: e.target.value === "true" })
                }
              />
            </Field>
            <Button
              disabled={busy}
              onClick={() =>
                write(
                  { kind: "auto_os", enabled: value.auto_os },
                  "Automatic OS selection verified.",
                )
              }
            >
              Apply automatic selection
            </Button>
          </div>
        </Panel>
      </div>
      <Panel title="Sleep timers">
        <div className="fields">
          {[
            ["bluetooth", "Bluetooth sleep"],
            ["dongle", "Receiver sleep"],
            ["deep_bluetooth", "Bluetooth deep sleep"],
            ["deep_dongle", "Receiver deep sleep"],
          ].map(([key, label]) => (
            <Field key={key} label={`${label} (seconds)`}>
              <input
                type="number"
                min={key.startsWith("deep") ? 10 : 0}
                max="64800"
                value={value.sleep[key]}
                onChange={(e) =>
                  setValue({
                    ...value,
                    sleep: { ...value.sleep, [key]: Number(e.target.value) },
                  })
                }
              />
            </Field>
          ))}
        </div>
        <Button
          disabled={busy}
          primary
          onClick={() =>
            write(
              {
                kind: "sleep",
                bt: value.sleep.bluetooth,
                dongle: value.sleep.dongle,
                deep_bt: value.sleep.deep_bluetooth,
                deep_dongle: value.sleep.deep_dongle,
              },
              "Sleep timers read back.",
            )
          }
        >
          Apply timers
        </Button>
      </Panel>
    </>
  );
}
