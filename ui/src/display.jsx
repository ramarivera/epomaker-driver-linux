import React, { useRef, useState } from "react";
import { api, base64File } from "./api";
import { Button, Field, Panel, Select } from "./controls";
import DisplayLibrary from "./display-library";
import DisplayPreview from "./display-preview";
import SystemInfoRefresh from "./system-info-refresh";
export default function Display({ connected, transport, busy, run }) {
  const fileInput = useRef(null);
  const history = useRef({ past: [], future: [] });
  const [sourceName, setSourceName] = useState("");
  const [file, setFile] = useState(null),
    [prepared, setPrepared] = useState(null),
    [kind, setKind] = useState("screen"),
    [bank, setBank] = useState(0),
    [delay, setDelay] = useState("");
  const animationNeedsUsb = kind === "animation" && transport !== "usb";
  const resetHistory = () => {
    history.current = { past: [], future: [] };
  };
  const keepHistory = (entries) => {
    // Bound each undo/redo stack; see docs/display.md.
    const recent = entries.slice(-10);
    const size = (draft) =>
      draft.content.length +
      (draft.preview_frames || [draft.preview_png]).reduce(
        (n, png) => n + png.length,
        0,
      );
    let bytes = recent.reduce((sum, draft) => sum + size(draft), 0);
    while (recent.length && bytes > 32 * 1024 * 1024)
      bytes -= size(recent.shift());
    return recent;
  };
  const useDraft = (asset) => {
    setPrepared(asset);
    setKind(asset.kind);
    setDelay(asset.delay_ms === null ? "" : String(asset.delay_ms));
    const bytes = Uint8Array.from(atob(asset.content), (character) =>
      character.charCodeAt(0),
    );
    setFile(new File([bytes], sourceName || "Edited display"));
    if (fileInput.current) fileInput.current.value = "";
  };
  const editFrame = async (operation, index, replacement) => {
    let success = false;
    await run(async () => {
      const result = await api("display_edit", {
        content: prepared.content,
        kind: prepared.kind,
        delay_ms: prepared.delay_ms,
        operation,
        index,
        ...(replacement === undefined ? {} : { replacement }),
      });
      history.current = {
        past: keepHistory([
          ...history.current.past,
          { ...prepared, selected_index: index },
        ]),
        future: [],
      };
      useDraft(result);
      success = true;
    });
    return success;
  };
  const restoreDraft = (direction) => {
    const source = history.current[direction];
    if (busy || !source.length) return;
    const target = direction === "past" ? "future" : "past";
    const next = source.pop();
    history.current[target] = keepHistory([
      ...history.current[target],
      prepared,
    ]);
    useDraft(next);
  };
  return (
    <>
      <Panel title="Screen image">
        <Button
          disabled={busy}
          onClick={() =>
            run(async () => {
              const canvas = document.createElement("canvas");
              canvas.width = 428;
              canvas.height = 142;
              const context = canvas.getContext("2d");
              context.fillStyle = "#000000";
              context.fillRect(0, 0, 428, 142);
              const content = canvas.toDataURL("image/png").split(",")[1];
              const result = await api("display_prepare", {
                content,
                kind: "screen",
              });
              resetHistory();
              setSourceName("Blank frame");
              useDraft({ ...result, content, kind: "screen" });
            })
          }
        >
          New blank draft
        </Button>
        <div className="fields">
          <Field label="Image file">
            <input
              type="file"
              ref={fileInput}
              accept="image/png,image/jpeg,image/gif,image/webp"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files[0];
                setFile(file || null);
                setSourceName(file?.name || "");
                setPrepared(null);
                resetHistory();
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
                resetHistory();
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
                  resetHistory();
                }}
              />
            </Field>
          )}
        </div>
        {sourceName && <p>Source: {sourceName}</p>}
        {prepared ? (
          <DisplayPreview prepared={prepared} busy={busy} onEdit={editFrame} />
        ) : (
          <div className="display-preview">
            <span>Prepare an image to preview the keyboard’s pixels.</span>
          </div>
        )}
        {prepared && (
          <>
            <div className="fields">
              <Button
                disabled={busy || !history.current.past.length}
                onClick={() => restoreDraft("past")}
              >
                Undo frame edit
              </Button>
              <Button
                disabled={busy || !history.current.future.length}
                onClick={() => restoreDraft("future")}
              >
                Redo frame edit
              </Button>
            </div>
            <p className="muted">
              Edits change this draft only. One remaining frame becomes a still
              image; inserting into a still image starts an animation at 80 ms
              per frame. Clear all leaves one black frame. Upload and library
              save are explicit.
            </p>
          </>
        )}
        <p className="muted">
          428 × 142 pixels · Images fit with black borders · Animations support
          up to 46 frames. Inspect converted RGB565 pixels before uploading.
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
        {kind === "animation" && (
          <p className="muted">
            Animation upload requires wired USB. You can prepare and preview it
            on any connection.
          </p>
        )}
        <div className="apply-row">
          <Button
            disabled={busy || !file}
            onClick={() =>
              run(async () => {
                setPrepared(null);
                resetHistory();
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
            disabled={!connected || busy || !prepared || animationNeedsUsb}
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
      <DisplayLibrary
        prepared={prepared}
        busy={busy}
        run={run}
        onLoad={(asset) => {
          resetHistory();
          useDraft(asset);
          setSourceName(asset.name);
        }}
      />
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
      <SystemInfoRefresh connected={connected} busy={busy} run={run} />
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
