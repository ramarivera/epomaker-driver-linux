import React, { useEffect, useRef, useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel } from "./controls";

const MAX_FILE_SIZE = 32 * 1024 * 1024;
const COMPONENT_LABELS = {
  main: "USB main",
  usb: "USB",
  rf: "RF",
  mled: "MLED",
  oled: "OLED",
  flash: "Flash",
  nordic: "Nordic",
};
const REASONS = {
  available: "Available",
  "missing-image": "Image not included",
  "unknown-current": "Current device version unknown",
  "not-newer": "Not newer than device",
  "unsupported-dispatch": "Updating this component is not implemented",
};

function valueOrUnknown(value) {
  return value === undefined || value === null || value === ""
    ? "Unknown"
    : String(value);
}

export default function Firmware({ busy, run, epoch, currentVersions }) {
  const [file, setFile] = useState(null);
  const [version, setVersion] = useState("");
  const [metadata, setMetadata] = useState(null);
  const [inspection, setInspection] = useState(null);
  const [fileError, setFileError] = useState(null);
  const request = useRef(0);

  useEffect(() => {
    request.current += 1;
    setInspection(null);
    return () => {
      request.current += 1;
    };
  }, [epoch, version, file, currentVersions]);

  const chooseFile = (event) => {
    request.current += 1;
    setInspection(null);
    const next = event.target.files?.[0] || null;
    if (next && next.size > MAX_FILE_SIZE) {
      setFile(null);
      setFileError("Firmware file must be 32 MiB or smaller");
      event.target.value = "";
      return;
    }
    setFileError(null);
    setFile(next);
  };

  const inspect = () => {
    const requestId = ++request.current;
    setInspection(null);
    run(async () => {
      if (!file) throw new Error("Choose a firmware file first");
      if (!version.trim() || version.length > 256)
        throw new Error(
          "Enter a nonempty vendor version (up to 256 characters)",
        );
      const content = await base64File(file);
      const data = { content, version };
      if (currentVersions) data.current_versions = currentVersions;
      const result = await api("firmware_inspect", data);
      if (requestId === request.current) setInspection(result);
    });
  };

  const inspectResult = inspection;
  const comparison = inspection?.comparison;
  return (
    <Panel title="Firmware file inspection" className="firmware-inspection">
      <p className="muted">
        Inspect a local vendor file without flashing or contacting the device.
      </p>
      <div className="fields">
        <Field label="Local firmware file">
          <input
            type="file"
            accept=".bin,.zip,.gz,application/octet-stream,application/zip"
            onChange={chooseFile}
          />
        </Field>
        <Field label="Vendor version">
          <input
            type="text"
            value={version}
            maxLength={256}
            placeholder="For example: usbv101_rfv12"
            onChange={(event) => setVersion(event.target.value)}
          />
        </Field>
      </div>
      <p>
        {file ? `${file.name} · ${file.size} bytes` : "No local file selected"}
      </p>
      {fileError && <p role="alert">{fileError}</p>}
      <Button disabled={busy || !file || !version.trim()} onClick={inspect}>
        Inspect local firmware
      </Button>
      <p className="muted">
        Checking metadata contacts the vendor service for Glyph model 3059. It
        does not download firmware.
      </p>
      <Button
        disabled={busy}
        onClick={() => {
          const requestId = ++request.current;
          run(async () => {
            setMetadata(null);
            const result = await api("firmware_metadata");
            if (requestId === request.current) setMetadata(result);
          });
        }}
      >
        Check vendor firmware metadata
      </Button>
      {metadata && (
        <div aria-label="Vendor firmware metadata">
          <p>Vendor version: {valueOrUnknown(metadata.version_str)}</p>
          <p>Vendor file path: {valueOrUnknown(metadata.file_path)}</p>
          <p className="muted">
            Metadata availability is informational; it does not download or
            verify a local file.
          </p>
        </div>
      )}
      {inspectResult && (
        <div aria-label="Firmware inspection result">
          <p>Inspected version: {valueOrUnknown(inspectResult.version)}</p>
          {Object.entries(inspectResult.components || {}).map(
            ([name, component]) => (
              <p key={name}>
                {COMPONENT_LABELS[name] || name}:{" "}
                {valueOrUnknown(component.length)} bytes · SHA-256{" "}
                {valueOrUnknown(component.sha256)}
              </p>
            ),
          )}
          <p className="muted">
            Structural inspection only. This does not flash firmware, prove
            authenticity, or verify model applicability.
          </p>
        </div>
      )}
      {comparison && (
        <div aria-label="Firmware version comparison">
          <p>Offline comparison for {valueOrUnknown(comparison.version)}</p>
          {(comparison.candidates || []).map((candidate) => (
            <p key={candidate.component}>
              {COMPONENT_LABELS[candidate.component] || candidate.component}:{" "}
              {candidate.candidate
                ? "Candidate"
                : REASONS[candidate.reason] || "Unavailable"}{" "}
              · observed {candidate.observed} · current{" "}
              {valueOrUnknown(candidate.current)}
            </p>
          ))}
          <p className="muted">
            Comparison is advisory and does not verify authenticity or model
            applicability.
          </p>
        </div>
      )}
    </Panel>
  );
}
