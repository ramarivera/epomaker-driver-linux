import React, { useEffect, useMemo, useState } from "react";
import { api, download } from "./api";
import { Button, Field, Panel, Select } from "./controls";

const validName = (value) => {
  const name = value.trim();
  return name && [...name].length <= 80 ? name : null;
};

export default function DisplayLibrary({
  prepared,
  busy = false,
  run = (operation) => operation(),
  onLoad,
}) {
  const [entries, setEntries] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [working, setWorking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const selected = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  );
  const locked = busy || working;

  const perform = async (operation) => {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      await run(async () => {
        try {
          await operation();
        } catch (operationError) {
          setError(operationError.message);
        }
      });
    } finally {
      setWorking(false);
    }
  };

  const refresh = () =>
    perform(async () => {
      const result = await api("display_library");
      const nextEntries = result.entries || [];
      setEntries(nextEntries);
      const refreshed = nextEntries.find((entry) => entry.id === selectedId);
      if (refreshed) setName(refreshed.name);
      else if (selectedId) {
        setSelectedId("");
        setName("");
      }
      setConfirmDelete(false);
    });

  useEffect(() => {
    refresh();
  }, []);

  const choose = (id) => {
    const entry = entries.find((candidate) => candidate.id === id) || null;
    setSelectedId(entry?.id || "");
    setName(entry?.name || "");
    setConfirmDelete(false);
    setMessage("");
    setError("");
  };

  const save = () => {
    const cleanName = validName(name);
    if (!cleanName) {
      setError("Asset name must be nonempty and at most 80 characters.");
      return;
    }
    if (!prepared) return;
    perform(async () => {
      const entry = await api("display_asset_save", {
        name: cleanName,
        kind: prepared.kind,
        delay_ms: prepared.delay_ms,
        content: prepared.content,
      });
      setEntries((current) => [...current, entry]);
      setSelectedId(entry.id);
      setName(entry.name);
      setConfirmDelete(false);
      setMessage(`Saved “${entry.name}” to the display asset library.`);
    });
  };

  const exportAsset = () => {
    if (!selected) return;
    perform(async () => {
      const value = await api("display_asset_export", { id: selected.id });
      download(`glyph-display-asset-${selected.id}.json`, value);
      setMessage("Display asset exported.");
    });
  };
  const importAsset = (event) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    perform(async () => {
      if (file.size > 20 * 1024 * 1024)
        throw new Error("Display asset file exceeds the 20 MiB limit.");
      let value;
      try {
        value = JSON.parse(await file.text());
      } catch {
        throw new Error("Display asset file is not valid JSON.");
      }
      const entry = await api("display_asset_import", { value });
      setEntries((current) => [...current, entry]);
      setSelectedId(entry.id);
      setName(entry.name);
      setConfirmDelete(false);
      setMessage(
        `Imported “${entry.name}”. Load it explicitly to replace the editor draft.`,
      );
    }).finally(() => {
      input.value = "";
    });
  };

  const load = () => {
    if (!selected) return;
    perform(async () => {
      const entry = await api("display_asset_get", { id: selected.id });
      onLoad(entry);
      setConfirmDelete(false);
      setMessage(
        `Loaded “${entry.name}” into the display editor. Upload remains a separate step.`,
      );
    });
  };

  const remove = () => {
    if (!selected) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      setMessage("Confirm deletion to remove this saved display asset.");
      return;
    }
    perform(async () => {
      await api("display_asset_delete", { id: selected.id });
      setEntries((current) =>
        current.filter((entry) => entry.id !== selected.id),
      );
      setSelectedId("");
      setName("");
      setConfirmDelete(false);
      setMessage("Display asset deleted. Nothing was uploaded to the device.");
    });
  };

  return (
    <Panel title="Display asset library">
      <p className="muted">
        Save prepared still images and animations for reuse. Library actions are
        offline and never upload to the device.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="fields">
        <Field label="Display asset">
          <Select
            aria-label="Display asset"
            value={selectedId}
            disabled={locked}
            options={[
              ["", "Choose an asset"],
              ...entries.map((entry) => [
                entry.id,
                `${entry.name} · ${entry.kind} · ${entry.frame_count} frame${entry.frame_count === 1 ? "" : "s"}`,
              ]),
            ]}
            onChange={(event) => choose(event.target.value)}
          />
        </Field>
      </div>
      <div className="fields">
        <Field label="Asset name">
          <input
            aria-label="Asset name"
            value={name}
            disabled={locked}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
      </div>
      <div className="apply-row">
        <Button disabled={locked} onClick={refresh}>
          Refresh display library
        </Button>
        <Button disabled={locked || !selected} onClick={load}>
          Load asset into editor
        </Button>
        <Button disabled={locked || !prepared} onClick={save}>
          Save prepared asset
        </Button>
        <Button
          disabled={locked || !selected}
          onClick={remove}
          aria-expanded={confirmDelete}
        >
          {confirmDelete ? "Confirm delete asset" : "Delete asset"}
        </Button>
        {confirmDelete && (
          <Button disabled={locked} onClick={() => setConfirmDelete(false)}>
            Cancel delete
          </Button>
        )}
      </div>
      <div className="fields">
        <Field label="Import display asset JSON">
          <input
            type="file"
            accept="application/json,.json"
            disabled={locked}
            onChange={importAsset}
          />
        </Field>
      </div>
      <div className="apply-row">
        <Button disabled={locked || !selected} onClick={exportAsset}>
          Export display asset JSON
        </Button>
      </div>
      <p className="muted">
        Import creates a new library entry and leaves the editor draft
        unchanged. This format is independent of vendor configuration files.
      </p>
      {selected && (
        <p className="muted">
          {selected.kind} · {selected.frame_count} frame
          {selected.frame_count === 1 ? "" : "s"} · {selected.pixel_bytes} pixel
          bytes. Loading changes the editor draft; upload is still explicit.
        </p>
      )}
    </Panel>
  );
}
