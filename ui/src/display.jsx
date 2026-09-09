import React, { useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel, Select } from "./controls";
export default function Display({ connected, busy, run }) {
  const [file, setFile] = useState(null),
    [prepared, setPrepared] = useState(null),
    [kind, setKind] = useState("screen"),
    [bank, setBank] = useState(0),
    [delay, setDelay] = useState("");
  return (
    <>
      <Panel title="Screen image">
        <div className="fields">
          <Field label="Image file">
            <input
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files[0];
                setFile(file || null);
                setPrepared(null);
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
              disabled={busy}
              onChange={(e) => {
                setKind(e.target.value);
                setPrepared(null);
              }}
            />
          </Field>
          {kind === "screen" && (
            <Field label="Still image bank">
              <Select
                value={bank}
                disabled={busy}
                options={[0, 1, 2, 3, 4].map((i) => [i, `Bank ${i + 1}`])}
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
                disabled={busy}
                step="1"
                onChange={(e) => {
                  setDelay(e.target.value);
                  setPrepared(null);
                }}
              />
            </Field>
          )}
        </div>
        <div className="display-preview">
          {prepared ? (
            <img
              src={`data:image/png;base64,${prepared.preview_png}`}
              alt="Prepared display pixels, first frame"
            />
          ) : (
            <span>Prepare an image to preview the keyboard’s pixels.</span>
          )}
        </div>
        <p className="muted">
          428 × 142 pixels · Images fit with black borders · Animations support
          up to 46 frames. The preview shows the first frame after RGB565
          conversion.
        </p>
        {prepared && (
          <p role="status">
            {prepared.frame_count}{" "}
            {prepared.frame_count === 1 ? "frame" : "frames"} ·{" "}
            {prepared.pixel_bytes.toLocaleString()} pixel bytes
            {prepared.delay_ms !== null &&
              ` · ${prepared.delay_ms} ms per frame`}
          </p>
        )}
        <div className="apply-row">
          <Button
            disabled={busy || !file}
            onClick={() =>
              run(async () => {
                setPrepared(null);
                if (file.size > 14 * 1024 * 1024)
                  throw new Error("Choose an image smaller than 14 MiB");
                const delayMs = delay === "" ? null : Number(delay);
                if (
                  kind === "animation" &&
                  delayMs !== null &&
                  (!Number.isInteger(delayMs) || delayMs < 0 || delayMs > 255)
                )
                  throw new Error(
                    "Frame delay must be an integer from 0 to 255 ms",
                  );
                const content = await base64File(file);
                const result = await api("display_prepare", {
                  kind,
                  content,
                  delay_ms: delayMs,
                });
                setPrepared({ ...result, content, kind });
              })
            }
          >
            Prepare preview
          </Button>
          <Button
            primary
            disabled={!connected || busy || !prepared}
            onClick={() =>
              run(
                () =>
                  api("write", {
                    kind: prepared.kind,
                    bank,
                    content: prepared.content,
                    delay_ms: prepared.delay_ms,
                  }),
                "Image transfer finished. Check the keyboard display.",
              )
            }
          >
            Upload to display
          </Button>
        </div>
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
    </>
  );
}
