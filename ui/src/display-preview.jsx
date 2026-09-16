import React, { useEffect, useState } from "react";
import { Button, Field, Select } from "./controls";

// Preview actual wire pixels from media.py; upload data remains owned by Display.
export default function DisplayPreview({ prepared, busy }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const frames = prepared.preview_frames || [prepared.preview_png];
  const current = Math.min(index, frames.length - 1);
  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [prepared]);
  useEffect(() => {
    const stopWhenHidden = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener("visibilitychange", stopWhenHidden);
    return () =>
      document.removeEventListener("visibilitychange", stopWhenHidden);
  }, []);
  useEffect(() => {
    if (!playing || busy || frames.length < 2 || prepared.delay_ms <= 0) return;
    const timer = setInterval(
      () => setIndex((value) => (value + 1) % frames.length),
      prepared.delay_ms,
    );
    return () => clearInterval(timer);
  }, [playing, busy, prepared, frames.length]);
  return (
    <>
      <div className="display-preview">
        <img
          src={`data:image/png;base64,${frames[current]}`}
          alt={
            current === 0
              ? "Prepared display pixels, first frame"
              : `Prepared display pixels, frame ${current + 1}`
          }
        />
      </div>
      {frames.length > 1 && (
        <>
          <div className="fields">
            <Field label="Preview frame">
              <Select
                value={current}
                disabled={busy}
                options={frames.map((_, frame) => [
                  frame,
                  `${frame + 1} of ${frames.length}`,
                ])}
                onChange={(event) => {
                  setPlaying(false);
                  setIndex(Number(event.target.value));
                }}
              />
            </Field>
            <Button
              disabled={busy || current === 0}
              onClick={() => {
                setPlaying(false);
                setIndex(current - 1);
              }}
            >
              Previous frame
            </Button>
            <Button
              disabled={busy || current === frames.length - 1}
              onClick={() => {
                setPlaying(false);
                setIndex(current + 1);
              }}
            >
              Next frame
            </Button>
            <Button
              disabled={busy || prepared.delay_ms <= 0}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? "Pause preview" : "Play preview"}
            </Button>
          </div>
          <p className="muted">
            Desktop preview timing is approximate; it does not verify keyboard
            playback.
            {prepared.delay_ms === 0 &&
              " Zero frame delay has no verified playback timing. Inspect frames individually."}
          </p>
        </>
      )}
    </>
  );
}
