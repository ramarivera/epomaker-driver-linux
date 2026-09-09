import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";
import { centeredCrop, DEFAULT_RATIO, SCREEN_RATIOS } from "./live-light-crop";

const WIDTH = 21;
const HEIGHT = 6;
const INTERVAL = 100;

export function frameColors(context) {
  const pixels = context.getImageData(0, 0, WIDTH, HEIGHT).data;
  let output = "";
  for (let i = 0; i < pixels.length; i += 4) {
    const alpha = pixels[i + 3] / 255;
    const channels = [pixels[i], pixels[i + 1], pixels[i + 2]].map((value) =>
      Math.round(value * alpha),
    );
    output += channels
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
  }
  return output;
}

export default function LiveLighting({
  connected,
  transport,
  lightSync,
  busy,
  screenRatio,
  onScreenRatioChange,
}) {
  const [running, setRunning] = useState(false);
  const [starting, setStarting] = useState(false);
  const [sampleCount, setSampleCount] = useState(0);
  const [error, setError] = useState(null);
  const ratioRef = useRef(screenRatio);
  ratioRef.current = screenRatio;
  const [preview, setPreview] = useState(null);
  const [frameSize, setFrameSize] = useState(null);
  const generation = useRef(0);
  const attempt = useRef(null);

  const supported = connected && transport === "usb" && lightSync === true;
  const cleanup = useCallback(async (current, message = null) => {
    if (!current || current.cleaned) return;
    current.cleaned = true;
    const isCurrent = attempt.current === current;
    if (isCurrent) generation.current += 1;
    if (current.timer !== null) clearTimeout(current.timer);
    current.timer = null;
    current.video?.pause();
    if (current.video) current.video.srcObject = null;
    current.stream?.getTracks().forEach((track) => track.stop());
    if (isCurrent) {
      attempt.current = null;
      setRunning(false);
      setStarting(false);
      setPreview(null);
      setFrameSize(null);
      if (message) setError(message);
    }
    if (current.session) {
      try {
        await api("live_light_stop", { session: current.session });
      } catch (stopError) {
        if (isCurrent) setError(`Cleanup failed: ${stopError.message}`);
      }
    }
  }, []);
  const stop = useCallback(
    (message = null) => cleanup(attempt.current, message),
    [cleanup],
  );

  const start = async () => {
    if (!supported || busy || running || starting || attempt.current) return;
    setError(null);
    setSampleCount(0);
    setStarting(true);
    const current = {
      generation: ++generation.current,
      stream: null,
      video: null,
      session: null,
      canvas: null,
      timer: null,
      cleaned: false,
    };
    attempt.current = current;
    let captured;
    try {
      if (!navigator.mediaDevices?.getDisplayMedia)
        throw new Error("Screen capture is unavailable in this browser.");
      captured = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });
      current.stream = captured;
      if (current.generation !== generation.current || !supported) {
        captured.getTracks().forEach((track) => track.stop());
        return;
      }
      const selected = document.createElement("video");
      selected.muted = true;
      selected.playsInline = true;
      selected.srcObject = captured;
      current.video = selected;
      captured.getTracks().forEach((track) =>
        track.addEventListener(
          "ended",
          () => cleanup(current, "Screen capture ended."),
          {
            once: true,
          },
        ),
      );
      await selected.play();
      if (current.generation !== generation.current || !supported) {
        await cleanup(current);
        return;
      }
      const created = await api("live_light_start", {});
      if (
        current.generation !== generation.current ||
        !supported ||
        attempt.current !== current
      ) {
        try {
          await api("live_light_stop", { session: created.session });
        } catch (stopError) {
          setError(`Cleanup failed: ${stopError.message}`);
        }
        await cleanup(current);
        return;
      }
      current.session = created.session;
      setStarting(false);
      current.canvas = document.createElement("canvas");
      current.canvas.width = WIDTH;
      current.canvas.height = HEIGHT;
      setRunning(true);
      const captureFrame = async () => {
        if (
          current.generation !== generation.current ||
          attempt.current !== current ||
          !current.session
        )
          return;
        try {
          const context = current.canvas.getContext("2d", {
            willReadFrequently: true,
          });
          const size = [selected.videoWidth, selected.videoHeight];
          const bounds = centeredCrop(ratioRef.current, ...size);
          context.drawImage(selected, ...bounds, 0, 0, WIDTH, HEIGHT);
          const colors = frameColors(context);
          await api("live_light_frame", {
            session: current.session,
            colors,
          });
          if (
            current.generation === generation.current &&
            attempt.current === current
          ) {
            setSampleCount((count) => count + 1);
            setPreview(colors.match(/.{6}/g));
            setFrameSize({ size, bounds });
          }
          if (
            current.generation === generation.current &&
            attempt.current === current
          )
            current.timer = setTimeout(captureFrame, INTERVAL);
        } catch (frameError) {
          if (
            current.generation === generation.current &&
            attempt.current === current
          )
            await cleanup(current, frameError.message);
        }
      };
      captureFrame();
    } catch (captureError) {
      captured?.getTracks().forEach((track) => track.stop());
      if (
        current.generation === generation.current &&
        attempt.current === current
      )
        await cleanup(current, captureError.message);
    }
  };

  useEffect(() => {
    if (!supported && attempt.current) cleanup(attempt.current);
  }, [supported, cleanup]);
  useEffect(() => () => cleanup(attempt.current), [cleanup]);

  return (
    <Panel title="Live screen lighting">
      {!supported && (
        <p className="muted">
          Live screen lighting requires a USB keyboard whose firmware reports
          light sync capability.
        </p>
      )}
      <p className="muted">
        Choose a centered crop for the selected screen, window or tab. Changes
        take effect on the next frame. Stop and start again to choose another
        capture source.
      </p>
      <div className="fields">
        <Field label="Screen crop ratio">
          <Select
            value={screenRatio}
            options={SCREEN_RATIOS}
            disabled={busy}
            onChange={(event) => onScreenRatioChange(event.target.value)}
          />
        </Field>
      </div>
      <Button
        disabled={busy}
        onClick={() => onScreenRatioChange(DEFAULT_RATIO)}
      >
        Reset screen crop ratio
      </Button>
      {frameSize && (
        <p className="muted">
          Source {frameSize.size[0]}×{frameSize.size[1]} · Crop{" "}
          {frameSize.bounds[2]}×{frameSize.bounds[3]} at {frameSize.bounds[0]},{" "}
          {frameSize.bounds[1]}
        </p>
      )}
      {preview && (
        <svg
          role="img"
          aria-label="Live RGB color preview, 21 columns by 6 rows"
          viewBox="0 0 21 6"
          style={{ width: "100%", maxWidth: 420, display: "block" }}
        >
          {preview.map((color, index) => (
            <rect
              key={index}
              x={index % 21}
              y={Math.floor(index / 21)}
              width="1"
              height="1"
              fill={`#${color}`}
            />
          ))}
        </svg>
      )}
      <div className="live-lighting">
        <Button
          disabled={!supported || busy || running || starting}
          onClick={start}
        >
          Start screen lighting
        </Button>
        <Button
          disabled={busy || (!running && !starting)}
          onClick={() => stop()}
        >
          Stop screen lighting
        </Button>
        <span className="muted">
          {starting
            ? "Preparing screen capture…"
            : running
              ? `Capturing screen · ${sampleCount} samples · up to 10 fps`
              : "Screen capture is stopped when leaving this page."}
        </span>
        <p className="muted">
          Stopping restores the lighting state saved when screen lighting
          started.
        </p>
        {error && <p className="notice error">{error}</p>}
      </div>
    </Panel>
  );
}
