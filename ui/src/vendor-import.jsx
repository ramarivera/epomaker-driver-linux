import React, { useEffect, useRef, useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel } from "./controls";

const MAX_FILE_SIZE = 8 * 1024 * 1024;

export default function VendorImport({
  layer,
  profile,
  connected,
  epoch = 0,
  busy = false,
  onApply,
}) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [token, setToken] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const mounted = useRef(true);
  const generation = useRef(0);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  useEffect(() => {
    generation.current += 1;
    setWorking(false);
    setPreview(null);
    setToken("");
    setMessage("");
  }, [layer, profile, connected, epoch, file]);
  const locked = busy || working;
  const chooseFile = (event) => {
    const next = event.target.files?.[0] || null;
    setFile(next);
    setPreview(null);
    setToken("");
    setError(
      next && next.size > MAX_FILE_SIZE
        ? "Vendor configuration files must be 8 MiB or smaller."
        : "",
    );
    setMessage("");
  };
  const previewFile = async () => {
    if (!file || file.size > MAX_FILE_SIZE || !connected) return;
    setWorking(true);
    setError("");
    setMessage("");
    const requestGeneration = ++generation.current;
    setPreview(null);
    setToken("");
    try {
      const result = await api("vendor_import_preview", {
        content: await base64File(file),
        target: layer,
        profile: layer === "Main" ? profile : 0,
      });
      if (!mounted.current || requestGeneration !== generation.current) return;
      setPreview(result.plan);
      setToken(result.token);
      setMessage("Preview ready. No keyboard settings have changed.");
    } catch (previewError) {
      if (mounted.current && requestGeneration === generation.current)
        setError(previewError.message);
    } finally {
      if (mounted.current && requestGeneration === generation.current)
        setWorking(false);
    }
  };
  const apply = () => {
    if (!token || !preview) return;
    setWorking(true);
    setError("");
    setMessage("");
    const requestGeneration = ++generation.current;
    setPreview(null);
    setToken("");
    Promise.resolve(onApply(token))
      .then((result) => {
        if (mounted.current && requestGeneration === generation.current) {
          setMessage(
            `Imported configuration. Recovery copy: ${result?.previous_configuration || "saved by the driver"}.`,
          );
        }
      })
      .catch((applyError) => {
        if (mounted.current && requestGeneration === generation.current)
          setError(applyError.message);
      })
      .finally(() => {
        if (mounted.current && requestGeneration === generation.current)
          setWorking(false);
      });
  };
  return (
    <Panel title="Import vendor configuration">
      <p className="muted">
        Preview a vendor JSON, DAT, or compressed configuration before replacing
        the selected {layer} keymap. Every import starts from the normal Glyph
        factory keymap, including Fn imports. An empty Fn configuration does not
        restore the Windows or Mac Fn defaults. Macro slots are assigned during
        preview.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="fields">
        <Field label="Vendor configuration file">
          <input
            aria-label="Vendor configuration file"
            type="file"
            disabled={locked}
            onChange={chooseFile}
          />
        </Field>
        <Button
          disabled={locked || !file || file.size > MAX_FILE_SIZE || !connected}
          onClick={previewFile}
        >
          Preview import
        </Button>
      </div>
      {!connected && (
        <p className="muted">
          Connect the Glyph keyboard to preview an import.
        </p>
      )}
      {preview && (
        <div className="muted">
          <p>
            Target: {preview.target} · Profile {preview.profile + 1}
          </p>
          <p>
            {Object.keys(preview.macros).length} macro assignments ·{" "}
            {preview.reserved_slots.length} reserved macro slots
          </p>
          <p>
            Apply replaces the selected keymap and writes its allocated macro
            payloads. A recovery copy is created before applying.
          </p>
        </div>
      )}
      <div className="apply-row">
        <Button
          primary
          disabled={locked || !token || !preview || !connected}
          onClick={apply}
        >
          Apply preview to keyboard
        </Button>
      </div>
    </Panel>
  );
}
