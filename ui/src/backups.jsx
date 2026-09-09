import React, { useEffect, useState } from "react";
import { api, download } from "./api";
import { Button, Field, Panel } from "./controls";
export default function Backups({ ui, identity, connected, busy, run, epoch }) {
  const schemas = ui?.backup_schemas ?? [2, 3];
  const limitations = ui?.backup_limitations ?? [
    "Screen images and unreferenced macro slots are not included.",
  ];
  const [value, setValue] = useState(null),
    [name, setName] = useState(""),
    [recovery, setRecovery] = useState("");
  useEffect(() => {
    setValue(null);
    setName("");
    setRecovery("");
  }, [epoch, identity?.device_id]);
  return (
    <>
      <Panel title="Save configuration">
        <p>
          Download keymaps, referenced macros, custom colors and keyboard
          settings.
        </p>
        <ul className="muted">
          {limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <Button
          primary
          disabled={!connected || busy}
          onClick={() =>
            run(
              async () =>
                download(
                  `epomaker-${identity?.device_id || "keyboard"}-backup.json`,
                  await api("read", { section: "backup" }),
                ),
              "Backup downloaded.",
            )
          }
        >
          Download backup
        </Button>
      </Panel>
      <Panel title="Restore configuration">
        <Field label="Backup file">
          <input
            type="file"
            accept=".json"
            onChange={(e) => {
              const file = e.target.files[0];
              setValue(null);
              if (file)
                run(async () => {
                  const value = JSON.parse(await file.text());
                  if (!schemas.includes(value.schema_version))
                    throw new Error(
                      `Choose a snapshot with schema ${schemas.join(" or ")}`,
                    );
                  if (value.identity?.device_id !== identity?.device_id)
                    throw new Error(
                      "Snapshot device identity does not match the connected device",
                    );
                  setValue(value);
                  setName(file.name);
                });
            }}
          />
        </Field>
        {value && (
          <p>
            {name} · Snapshot version {value.schema_version}
          </p>
        )}
        <p className="muted">
          Current configuration is saved to a recovery file before restoration.
          A disconnect can leave a partial restore.
        </p>
        <Button
          disabled={!connected || busy || !value}
          onClick={() =>
            run(async () => {
              const result = await api("write", { kind: "restore", value });
              setRecovery(result.previous_configuration);
            }, "Restoration verified.")
          }
        >
          Restore backup
        </Button>
        {recovery && <p className="recovery">Recovery copy: {recovery}</p>}
      </Panel>
    </>
  );
}
