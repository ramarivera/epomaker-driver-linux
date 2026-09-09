import React, { useEffect, useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel, Select } from "./controls";
export default function Display({ ui, connected, busy, run }) {
  const [file, setFile] = useState(null),
    [preview, setPreview] = useState(""),
    [kind, setKind] = useState("screen"),
    [bank, setBank] = useState(0),
    [delay, setDelay] = useState("");
  const controls = ui?.controls || [
    "display",
    "clock",
    "system_info",
    "display_language_toggle",
  ];
  const has = (name) => controls.includes(name);
  const spec = ui?.display;
  const banks = Number.isInteger(spec?.banks) ? spec.banks : 5;
  const maxFrames = Number.isInteger(spec?.max_frames) ? spec.max_frames : 46;
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return (
    <>
      {has("display") && spec && (
        <Panel title="Screen image">
          <div className="fields">
            <Field label="Image file">
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                onChange={(e) => {
                  const file = e.target.files[0];
                  setFile(file || null);
                  if (file)
                    setKind(file.type === "image/gif" ? "animation" : "screen");
                }}
              />
            </Field>
            <Field label="Upload as">
              <Select
                value={kind}
                options={[
                  ["screen", "Still image"],
                  ["animation", "Animation"],
                ]}
                onChange={(e) => setKind(e.target.value)}
              />
            </Field>
            {kind === "screen" && (
              <Field label="Still image bank">
                <Select
                  value={bank}
                  options={Array.from({ length: banks }, (_, i) => [
                    i,
                    `Bank ${i + 1}`,
                  ])}
                  onChange={(e) => setBank(Number(e.target.value))}
                />
              </Field>
            )}
            {kind === "animation" && (
              <Field label="Frame delay (ms, optional)">
                <input
                  type="number"
                  min="0"
                  max="255"
                  placeholder="Average from file"
                  value={delay}
                  onChange={(e) => setDelay(e.target.value)}
                />
              </Field>
            )}
          </div>
          <div className="display-preview">
            {preview ? (
              <img src={preview} alt="Selected display image preview" />
            ) : (
              <span>Select an image to preview it.</span>
            )}
          </div>
          <p className="muted">
            {spec.width} × {spec.height} pixels · Images fit with black borders
            · Animations support up to {maxFrames} frames.
          </p>
          <Button
            primary
            disabled={!connected || busy || !file}
            onClick={() =>
              run(async () => {
                if (file.size > 14 * 1024 * 1024)
                  throw new Error("Choose an image smaller than 14 MiB");
                await api("write", {
                  kind,
                  bank,
                  content: await base64File(file),
                  delay_ms: delay === "" ? null : Number(delay),
                });
              }, "Image transfer finished. Check the keyboard display.")
            }
          >
            Upload to display
          </Button>
        </Panel>
      )}
      {(has("clock") || has("system_info")) && (
        <Panel title="Clock and system information">
          <p className="muted">
            Send the current local time or a sample of this computer’s
            statistics.
          </p>
          <div className="fields">
            {has("clock") && (
              <Button
                disabled={!connected || busy}
                onClick={() =>
                  run(() => api("write", { kind: "clock" }), "Clock sent.")
                }
              >
                Sync clock
              </Button>
            )}
            {has("system_info") && (
              <Button
                disabled={!connected || busy}
                onClick={() =>
                  run(
                    () => api("write", { kind: "system_info" }),
                    "System information sent.",
                  )
                }
              >
                Send system information
              </Button>
            )}
          </div>
        </Panel>
      )}
      {has("display_language_toggle") && (
        <Panel title="Display language">
          <p className="muted">
            Switch between the keyboard’s English and Chinese display text. The
            current language cannot be read back.
          </p>
          <Button
            disabled={!connected || busy}
            onClick={() =>
              run(
                () => api("write", { kind: "display_language_toggle" }),
                "Language toggle sent. Check the keyboard display.",
              )
            }
          >
            Toggle display language
          </Button>
        </Panel>
      )}
    </>
  );
}
