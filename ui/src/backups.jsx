import React, { useState } from "react";
import { api, download } from "./api";
import { Button, Field, Panel } from "./controls";
export default function Backups({ connected, busy, run, onConnectionLost }) {
  const [value, setValue] = useState(null),
    [name, setName] = useState(""),
    [recovery, setRecovery] = useState(""),
    [resetResult, setResetResult] = useState(null),
    [resetConfirmed, setResetConfirmed] = useState(false);
  return (
    <>
      <Panel title="Save configuration">
        <p>
          Download keymaps, all 256 macro slots, custom colors and keyboard
          settings.
        </p>
        <p className="muted">Screen images are not included.</p>
        <Button
          primary
          disabled={!connected || busy}
          onClick={() =>
            run(
              async () =>
                download(
                  "glyph-backup.json",
                  await api("read", { section: "backup" }),
                ),
              "Backup downloaded.",
            )
          }
        >
          Download backup
        </Button>
      </Panel>
      <Panel title="Factory reset Glyph">
        <p>
          Save keymaps, all macro slots, custom colors and settings, then send
          the Glyph factory-reset command. Screen images are not backed up.
        </p>
        <p className="muted">
          The keyboard will be disconnected after the attempt. Reconnect it to
          continue. Factory defaults are not verified automatically.
        </p>
        <label>
          <input
            type="checkbox"
            checked={resetConfirmed}
            onChange={(e) => setResetConfirmed(e.target.checked)}
          />{" "}
          I understand that factory reset changes the keyboard configuration.
        </label>
        <Button
          disabled={!connected || busy || !resetConfirmed}
          onClick={() => {
            setResetResult(null);
            setResetConfirmed(false);
            run(async () => {
              try {
                const result = await api("write", { kind: "factory_reset" });
                onConnectionLost();
                setRecovery(result.previous_configuration);
                setResetResult(result);
              } catch (error) {
                // The server drops stale state even when reset or its backup
                // fails, so reconnect is required for every reset response.
                onConnectionLost();
                throw error;
              }
            }, "Factory reset sent. Reconnect to continue; defaults were not verified.");
          }}
        >
          Factory reset Glyph
        </Button>
        {resetResult && (
          <p className="recovery" role="status">
            Reset command sent. Reconnect required. Recovery copy:{" "}
            {resetResult.previous_configuration}
          </p>
        )}
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
                  if (
                    ![2, 3].includes(value.schema_version) ||
                    value.identity?.device_id !== 3059
                  )
                    throw new Error("Choose a Glyph version 2 or 3 snapshot");
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
