import React, { useEffect, useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel, Select } from "./controls";
export default function Display({ connected, busy, run }) {
  const [file, setFile] = useState(null),
    [preview, setPreview] = useState(""),
    [kind, setKind] = useState("screen"),
    [delay, setDelay] = useState("");
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
          428 × 142 pixels · Images fit with black borders · Animations support
          up to 46 frames.
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
                content: await base64File(file),
                delay_ms: delay === "" ? null : Number(delay),
              });
            }, "Image transfer finished. Check the keyboard display.")
          }
        >
          Upload to display
        </Button>
      </Panel>
      <Panel title="Clock and system information">
        <p className="muted">
          Send the current local time or a sample of this computer’s statistics.
        </p>
        <div className="fields">
          <Button
            disabled={!connected || busy}
            onClick={() =>
              run(() => api("write", { kind: "clock" }), "Clock sent.")
            }
          >
            Sync clock
          </Button>
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
        </div>
      </Panel>
    </>
  );
}
