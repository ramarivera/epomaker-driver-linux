import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";

function validName(value) {
  const name = value.trim();
  return name && [...name].length <= 20 ? name : null;
}

export default function ConfigLibrary({
  matrix,
  layer,
  connected,
  busy = false,
  onPreview,
  onApply,
}) {
  const [entries, setEntries] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const selected = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  );
  const locked = busy || working;
  const sameLayer = selected?.layer === layer;

  const refresh = async () => {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await api("config_library");
      if (!mounted.current) return;
      const next = result.entries || [];
      setEntries(next);
      const refreshed = next.find((entry) => entry.id === selectedId);
      if (refreshed) setName(refreshed.name);
      else if (selectedId) {
        setSelectedId("");
        setName("");
      }
    } catch (refreshError) {
      if (mounted.current) setError(refreshError.message);
    } finally {
      if (mounted.current) setWorking(false);
    }
  };
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    setMessage("");
  }, [layer]);

  const choose = (entry) => {
    setSelectedId(entry?.id || "");
    setName(entry?.name || "");
    setMessage("");
    setError("");
  };
  const save = async ({
    update = false,
    savedMatrix = matrix,
    savedLayer = layer,
  } = {}) => {
    const cleanName = validName(name);
    if (!cleanName) {
      setError(
        "Configuration name must be nonempty and at most 20 characters.",
      );
      return;
    }
    if (!/^[0-9a-fA-F]{1024}$/.test(savedMatrix)) {
      setError("The current keymap is incomplete and cannot be saved.");
      return;
    }
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const payload = {
        name: cleanName,
        matrix: savedMatrix,
        layer: savedLayer,
      };
      if (update) {
        payload.id = selected.id;
        payload.revision = selected.revision;
      }
      const saved = await api("config_library_save", payload);
      if (!mounted.current) return;
      setEntries((current) =>
        update
          ? current.map((entry) => (entry.id === saved.id ? saved : entry))
          : [...current, saved],
      );
      setSelectedId(saved.id);
      setName(saved.name);
      setMessage(
        update
          ? `Updated “${saved.name}” in the library.`
          : `Saved “${saved.name}” to the library.`,
      );
    } catch (saveError) {
      if (mounted.current) setError(saveError.message);
    } finally {
      if (mounted.current) setWorking(false);
    }
  };
  const rename = () =>
    selected &&
    save({
      update: true,
      savedMatrix: selected.matrix,
      savedLayer: selected.layer,
    });
  const preview = () => {
    if (!selected || !sameLayer) return;
    onPreview(selected.matrix);
    setMessage(
      `Previewing “${selected.name}”. Nothing was written to the keyboard.`,
    );
  };
  const apply = () => {
    if (!selected || !sameLayer || !connected) return;
    setWorking(true);
    setError("");
    setMessage("");
    Promise.resolve(onApply(selected))
      .then(() => {
        if (mounted.current)
          setMessage(
            `Applied “${selected.name}” and verified the selected ${layer} matrix.`,
          );
      })
      .catch((applyError) => {
        if (mounted.current) setError(applyError.message);
      })
      .finally(() => {
        if (mounted.current) setWorking(false);
      });
  };
  const remove = async () => {
    if (!selected) return;
    setWorking(true);
    setError("");
    setMessage("");
    try {
      await api("config_library_delete", {
        id: selected.id,
        revision: selected.revision,
      });
      if (!mounted.current) return;
      setEntries((current) =>
        current.filter((entry) => entry.id !== selected.id),
      );
      setSelectedId("");
      setName("");
      setMessage("Configuration deleted. The keyboard was not changed.");
    } catch (deleteError) {
      if (mounted.current) setError(deleteError.message);
    } finally {
      if (mounted.current) setWorking(false);
    }
  };
  return (
    <Panel title="Named Glyph key configurations">
      <p className="muted">
        Save the current displayed layer configuration. An un-applied single-key
        draft is not included. Macro assignments reference slots; macro content
        is not copied. Cloud sharing is not supported yet.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="fields">
        <Field label="Configuration">
          <Select
            aria-label="Configuration"
            value={selectedId}
            disabled={locked}
            options={[
              ["", "Choose a configuration"],
              ...entries.map((entry) => [
                entry.id,
                `${entry.name} · ${entry.layer}`,
              ]),
            ]}
            onChange={(event) =>
              choose(entries.find((entry) => entry.id === event.target.value))
            }
          />
        </Field>
        <Button disabled={locked} onClick={refresh}>
          Refresh configurations
        </Button>
      </div>
      <div className="fields">
        <Field label="Configuration name">
          <input
            aria-label="Configuration name"
            value={name}
            disabled={locked}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Saved layer">
          <input
            aria-label="Saved layer"
            value={selected?.layer || layer}
            readOnly
          />
        </Field>
      </div>
      {selected && !sameLayer && (
        <p className="muted">
          Select the saved layer ({selected.layer}) above to preview or apply
          this configuration.
        </p>
      )}
      <div className="apply-row">
        <Button disabled={locked || !matrix} onClick={() => save()}>
          Save current configuration
        </Button>
        <Button disabled={locked || !selected} onClick={rename}>
          Rename selected
        </Button>
        <Button disabled={locked || !selected || !sameLayer} onClick={preview}>
          Load preview
        </Button>
        <Button
          primary
          disabled={locked || !selected || !sameLayer || !connected}
          onClick={apply}
        >
          Apply saved configuration
        </Button>
        <Button disabled={locked || !selected} onClick={remove}>
          Delete selected
        </Button>
      </div>
    </Panel>
  );
}
