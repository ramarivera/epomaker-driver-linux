import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";

export default function Settings({ ui, connected, busy, run, epoch }) {
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
  const controls = ui?.controls || [
    "settings",
    "options",
    "auto_os",
    "debounce",
    "sleep",
  ];
  const has = (name) => controls.includes(name);
  const profileCount = Number.isInteger(ui?.profiles) ? ui.profiles : 3;
  const sleepFields = ui?.sleep_fields || [
    "bluetooth",
    "dongle",
    "deep_bluetooth",
    "deep_dongle",
  ];
  const sleepLabels = {
    bluetooth: "Bluetooth sleep",
    dongle: "Receiver sleep",
    deep_bluetooth: "Bluetooth deep sleep",
    deep_dongle: "Receiver deep sleep",
  };
  const sleepLimits = ui?.sleep_limits || {};
  const sleepKey = {
    bluetooth: "bt",
    dongle: "dongle",
    deep_bluetooth: "deep_bt",
    deep_dongle: "deep_dongle",
  };

  return (
    <>
      <div className="two-columns">
        {(has("settings") || has("debounce")) && (
          <Panel title="Profile and response">
            {has("settings") && (
              <div className="fields">
                <Field label="Active profile">
                  <Select
                    value={value.profile}
                    options={Array.from({ length: profileCount }, (_, i) => [
                      i,
                      `Profile ${i + 1}`,
                    ])}
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
            )}
            {has("debounce") && (
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
        )}
        {(has("options") || has("auto_os")) && (
          <Panel title="Operating system">
            {has("options") && (
              <>
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
                          options: {
                            ...value.options,
                            wasd_swap: e.target.checked,
                          },
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
              </>
            )}
            {has("auto_os") && (
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
            )}
          </Panel>
        )}
      </div>
      {has("sleep") && (
        <Panel title="Sleep timers">
          <div className="fields">
            {sleepFields.map((key) => {
              const limit = sleepLimits[sleepKey[key]] || {};
              return (
                <Field key={key} label={`${sleepLabels[key] || key} (seconds)`}>
                  <input
                    type="number"
                    min={limit.min ?? 0}
                    max={limit.max ?? 64800}
                    value={value.sleep[key]}
                    onChange={(e) =>
                      setValue({
                        ...value,
                        sleep: {
                          ...value.sleep,
                          [key]: Number(e.target.value),
                        },
                      })
                    }
                  />
                </Field>
              );
            })}
          </div>
          <Button
            disabled={busy}
            primary
            onClick={() =>
              write(
                {
                  kind: "sleep",
                  ...Object.fromEntries(
                    sleepFields.map((key) => [sleepKey[key], value.sleep[key]]),
                  ),
                },
                "Sleep timers read back.",
              )
            }
          >
            Apply timers
          </Button>
        </Panel>
      )}
    </>
  );
}
