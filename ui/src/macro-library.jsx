import React, { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";

const MODES = [
  ["count", "Count"],
  ["toggle", "Toggle"],
  ["held", "While held"],
];
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const validName = (name) => {
  const trimmed = name.trim();
  return trimmed && [...trimmed].length <= 20 ? trimmed : null;
};

export default function MacroLibrary({
  value,
  busy = false,
  recorderPending = false,
  onWorkingChange,
  onLoad,
}) {
  const [entries, setEntries] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState("count");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const selected = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  );
  const locked = busy || recorderPending || working;
  useEffect(() => {
    onWorkingChange?.(working);
  }, [onWorkingChange, working]);
  const draftChanged = selected
    ? !same(value, selected.value)
    : Boolean(value?.events?.length || value?.repeat !== 1);

  const refresh = async () => {
    setWorking(true);
    setError("");
    try {
      const result = await api("macro_library");
      const nextEntries = result.entries || [];
      setEntries(nextEntries);
      const refreshed = nextEntries.find((entry) => entry.id === selectedId);
      if (refreshed) {
        setName(refreshed.name);
        setMode(refreshed.mode);
      } else if (selectedId) {
        setSelectedId("");
        setName("");
      }
    } catch (refreshError) {
      setError(refreshError.message);
    } finally {
      setWorking(false);
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  const choose = (entry) => {
    if (!entry) {
      setSelectedId("");
      setName("");
      setMode("count");
      return;
    }
    setSelectedId(entry.id);
    setName(entry.name);
    setMode(entry.mode);
    setMessage("");
    setError("");
  };
  const loadSelected = () => {
    if (!selected) return;
    if (
      draftChanged &&
      !window.confirm(
        "Replace the current macro draft with this library entry?",
      )
    )
      return;
    onLoad(selected.value);
    setMessage(
      `Loaded “${selected.name}” into the editor. Destination slot is unchanged.`,
    );
    setError("");
  };
  const save = async (update, useEditorValue, modeOverride = null) => {
    const cleanName = validName(name);
    if (!cleanName) {
      setError("Library name must be nonempty and at most 20 characters.");
      return;
    }
    setWorking(true);
    setError("");
    try {
      const payload = {
        name: cleanName,
        value: update && !useEditorValue ? selected.value : value,
        mode: modeOverride || mode,
      };
      if (update) {
        payload.id = selected.id;
        payload.revision = selected.revision;
      }
      const saved = await api("macro_library_save", payload);
      setEntries((current) =>
        update
          ? current.map((entry) => (entry.id === saved.id ? saved : entry))
          : [...current, saved],
      );
      setSelectedId(saved.id);
      setName(saved.name);
      setMode(saved.mode);
      setMessage(
        update
          ? `Updated “${saved.name}” in the library.`
          : `Saved “${saved.name}” to the library.`,
      );
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setWorking(false);
    }
  };
  const rename = async () => {
    if (!selected) return;
    await save(true, false, selected.mode);
  };
  const remove = async () => {
    if (
      !selected ||
      !window.confirm(
        `Delete library entry “${selected.name}”? This does not erase the device slot.`,
      )
    )
      return;
    setWorking(true);
    setError("");
    try {
      await api("macro_library_delete", {
        id: selected.id,
        revision: selected.revision,
      });
      setEntries((current) =>
        current.filter((entry) => entry.id !== selected.id),
      );
      setSelectedId("");
      setName("");
      setMessage(
        "Library entry deleted. The device macro slot was not changed.",
      );
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setWorking(false);
    }
  };
  return (
    <Panel title="Named macro library">
      <p className="muted">
        Save macros here for later. To use one on your keyboard, load it into
        the editor, save it to a slot, and assign that slot in Keymap.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="fields">
        <Field label="Library entry">
          <Select
            aria-label="Library entry"
            value={selectedId}
            disabled={locked}
            options={[
              ["", "Choose an entry"],
              ...entries.map((entry) => [
                entry.id,
                `${entry.name} · ${entry.mode}`,
              ]),
            ]}
            onChange={(event) =>
              choose(entries.find((entry) => entry.id === event.target.value))
            }
          />
        </Field>
        <Button disabled={locked || !selected} onClick={loadSelected}>
          Load into editor
        </Button>
        <Button disabled={locked} onClick={refresh}>
          Refresh library
        </Button>
      </div>
      <div className="fields">
        <Field label="Library name">
          <input
            aria-label="Library name"
            value={name}
            disabled={locked}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Playback preference">
          <Select
            aria-label="Playback preference"
            value={mode}
            disabled={locked}
            options={MODES}
            onChange={(event) => setMode(event.target.value)}
          />
        </Field>
      </div>
      <p className="muted">
        Choose the same playback setting when assigning this macro in Keymap.
      </p>
      <div className="apply-row">
        <Button disabled={locked || !value} onClick={() => save(false, true)}>
          Save as new library entry
        </Button>
        <Button
          disabled={locked || !selected || !value}
          onClick={() => save(true, true)}
        >
          Update selected entry
        </Button>
        <Button disabled={locked || !selected} onClick={rename}>
          Rename selected
        </Button>
        <Button disabled={locked || !selected} onClick={remove}>
          Delete selected
        </Button>
      </div>
      {selected && (
        <p className="muted">
          Rename keeps the saved sequence. Use Update selected entry to save
          changes from the editor.
        </p>
      )}
    </Panel>
  );
}
