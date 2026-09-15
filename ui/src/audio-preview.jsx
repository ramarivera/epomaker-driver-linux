import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";
import { frameColors } from "./live-lighting";
import {
  DEFAULT_RHYTHM_SETTINGS,
  RHYTHM_MODES,
  drawRhythm,
} from "./rhythm-renderer";
import defaultRhythmLayout, {
  RHYTHM_CANVAS,
  centerRhythmLayout,
  resetRhythmRotation,
  resetRhythmSize,
  sampleRhythm,
  setRhythmPosition,
  setRhythmRotation,
  setRhythmSize,
} from "./rhythm-layout";

const labels = {
  gain: "Gain",
  tilt: "Tilt",
  contrast: "Contrast",
  release: "Release",
  min_db: "Minimum dB",
  max_db: "Maximum dB",
  attack_frames: "Attack frames",
};
const settingOrder = [
  "gain",
  "tilt",
  "contrast",
  "release",
  "min_db",
  "max_db",
  "attack_frames",
];
const RHYTHM_DEFAULTS = DEFAULT_RHYTHM_SETTINGS;

export default function AudioPreview({
  busy = false,
  connected = false,
  transport,
  lightSync = false,
}) {
  const [defaults, setDefaults] = useState(null);
  const [limits, setLimits] = useState({});
  const [settings, setSettings] = useState({});
  const [rhythm, setRhythm] = useState(RHYTHM_DEFAULTS);
  const [rhythmLayout, setRhythmLayout] = useState(defaultRhythmLayout);
  const rhythmLayoutRef = useRef(rhythmLayout);
  rhythmLayoutRef.current = rhythmLayout;
  const rhythmRef = useRef(rhythm);
  rhythmRef.current = rhythm;
  const [outputs, setOutputs] = useState([]);
  const [target, setTarget] = useState("auto");
  const [bands, setBands] = useState(null);
  const [colors, setColors] = useState(null);
  const [sequence, setSequence] = useState(null);
  const [frameCount, setFrameCount] = useState(0);
  const [phase, setPhase] = useState("stopped");
  const [error, setError] = useState("");
  const [sendRhythm, setSendRhythm] = useState(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const attemptRef = useRef(null);
  const starting = useRef(false);
  const refreshing = useRef(false);
  const supported = connected && transport === "usb" && lightSync === true;

  const updateRhythmLayout = useCallback((update) => {
    try {
      const next = update(rhythmLayoutRef.current);
      rhythmLayoutRef.current = next;
      setRhythmLayout(next);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, []);

  useEffect(() => {
    let active = true;
    api("audio_config")
      .then((result) => {
        if (!active || !mounted.current) return;
        const next = result.defaults || {};
        setDefaults(next);
        setSettings({ ...next });
        setLimits(result.limits || {});
      })
      .catch((reason) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const stopAttempt = useCallback(async (attempt, reason = "") => {
    if (!attempt || attempt.stopped) return;
    attempt.stopped = true;
    if (attempt.timer !== null) clearTimeout(attempt.timer);
    const current = attemptRef.current === attempt;
    if (current) {
      generation.current++;
      attemptRef.current = null;
      starting.current = false;
      if (mounted.current) {
        setPhase("stopped");
        setBands(null);
        setColors(null);
        setSequence(null);
      }
    }
    const cleanupGeneration = generation.current;
    const failures = [];
    for (const [operation, session, fallback] of [
      ["audio_preview_stop", attempt.session, "Could not stop audio preview."],
      [
        "live_light_stop",
        attempt.lightSession,
        "Could not restore keyboard lighting.",
      ],
    ])
      if (session) {
        try {
          const result = await api(operation, { session });
          if (result?.ok === false || result?.error)
            failures.push(result.error || fallback);
        } catch (stopError) {
          failures.push(stopError.message);
        }
      }
    if (
      !mounted.current ||
      !current ||
      generation.current !== cleanupGeneration
    )
      return;
    if (failures.length) setError(`Cleanup failed: ${failures.join("; ")}`);
    else if (reason) setError(reason);
  }, []);

  const renderRhythm = useCallback((nextBands, attempt) => {
    const canvas = attempt.canvas || document.createElement("canvas");
    if (!attempt.canvas) {
      canvas.width = RHYTHM_CANVAS.width;
      canvas.height = RHYTHM_CANVAS.height;
    }
    attempt.canvas = canvas;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    drawRhythm(context, nextBands, rhythmRef.current, attempt.frameIndex++);
    const output = attempt.outputCanvas || document.createElement("canvas");
    if (!attempt.outputCanvas) {
      output.width = 21;
      output.height = 6;
    }
    attempt.outputCanvas = output;
    const scratch = attempt.scratchCanvas || document.createElement("canvas");
    if (!attempt.scratchCanvas) {
      scratch.width = RHYTHM_CANVAS.width;
      scratch.height = RHYTHM_CANVAS.height;
    }
    attempt.scratchCanvas = scratch;
    const outputContext = output.getContext("2d", { willReadFrequently: true });
    sampleRhythm(outputContext, canvas, rhythmLayoutRef.current, scratch);
    return frameColors(outputContext).match(/.{6}/g) || [];
  }, []);

  const stopLateSession = useCallback(
    async (operation, session, attempt, fallback) => {
      if (!session) return;
      try {
        const result = await api(operation, { session });
        const failure = result?.ok === false || result?.error;
        if (
          failure &&
          mounted.current &&
          attemptRef.current === null &&
          generation.current === attempt.generation + 1
        )
          setError(result.error || fallback);
      } catch (reason) {
        if (
          mounted.current &&
          attemptRef.current === null &&
          generation.current === attempt.generation + 1
        )
          setError(`Cleanup failed: ${reason.message}`);
      }
    },
    [],
  );

  const poll = useCallback(
    async (attempt) => {
      if (attempt.stopped || attemptRef.current !== attempt) return;
      try {
        const sample = await api("audio_preview_sample", {
          session: attempt.session,
        });
        if (
          attempt.stopped ||
          attemptRef.current !== attempt ||
          generation.current !== attempt.generation
        )
          return;
        if (sample.error) return stopAttempt(attempt, sample.error);
        if (sample.running === false) return stopAttempt(attempt);
        if (!Array.isArray(sample.bands)) {
          if (!attempt.stopped && attemptRef.current === attempt)
            attempt.timer = setTimeout(() => poll(attempt), 100);
          return;
        }
        const nextBands = sample.bands;
        const nextColors = renderRhythm(nextBands, attempt);
        setBands(nextBands);
        setColors(nextColors);
        setSequence(sample.sequence ?? null);
        setFrameCount((count) => count + 1);
        if (attempt.lightSession)
          await api("live_light_frame", {
            session: attempt.lightSession,
            colors: nextColors.join(""),
          });
        if (!attempt.stopped && attemptRef.current === attempt)
          attempt.timer = setTimeout(() => poll(attempt), 100);
      } catch (pollError) {
        if (!attempt.stopped && attemptRef.current === attempt)
          await stopAttempt(attempt, pollError.message);
      }
    },
    [renderRhythm, stopAttempt],
  );

  const start = async () => {
    if (starting.current || phase !== "stopped" || !defaults) return;
    const supported = connected && transport === "usb" && lightSync === true;
    const sending = sendRhythm && supported;
    starting.current = true;
    const attempt = {
      generation: ++generation.current,
      session: null,
      lightSession: null,
      sending,
      timer: null,
      canvas: null,
      outputCanvas: null,
      scratchCanvas: null,
      frameIndex: 0,
      stopped: false,
    };
    attemptRef.current = attempt;
    setPhase("starting");
    setError("");
    setBands(null);
    setColors(null);
    setSequence(null);
    setFrameCount(0);
    try {
      const result = await api("audio_preview_start", { target, settings });
      attempt.session = result.session;
      if (
        !mounted.current ||
        attemptRef.current !== attempt ||
        generation.current !== attempt.generation
      ) {
        await stopLateSession(
          "audio_preview_stop",
          attempt.session,
          attempt,
          "Could not stop audio preview.",
        );
        return;
      }
      if (sending) {
        const created = await api("live_light_start", {});
        if (
          !mounted.current ||
          attemptRef.current !== attempt ||
          generation.current !== attempt.generation ||
          attempt.stopped
        ) {
          await stopLateSession(
            "live_light_stop",
            created.session,
            attempt,
            "Could not restore keyboard lighting.",
          );
          return stopAttempt(attempt);
        }
        attempt.lightSession = created.session;
      }
      setPhase("running");
      await poll(attempt);
    } catch (startError) {
      if (attemptRef.current === attempt && mounted.current)
        await stopAttempt(attempt, startError.message);
      else {
        await stopLateSession(
          "audio_preview_stop",
          attempt.session,
          attempt,
          "Could not stop audio preview.",
        );
      }
    } finally {
      starting.current = false;
    }
  };

  useEffect(() => {
    const leave = () => {
      mounted.current = false;
      generation.current++;
      const attempt = attemptRef.current;
      if (attempt) {
        attempt.stopped = true;
        if (attempt.timer !== null) clearTimeout(attempt.timer);
        if (attempt.session)
          void api("audio_preview_stop", { session: attempt.session }).catch(
            () => {},
          );
        if (attempt.lightSession)
          void api("live_light_stop", { session: attempt.lightSession }).catch(
            () => {},
          );
      }
      attemptRef.current = null;
    };
    window.addEventListener("pagehide", leave);
    window.addEventListener("beforeunload", leave);
    return () => {
      leave();
      window.removeEventListener("pagehide", leave);
      window.removeEventListener("beforeunload", leave);
    };
  }, []);

  useEffect(() => {
    if (!supported && attemptRef.current?.sending)
      void stopAttempt(attemptRef.current);
  }, [supported, stopAttempt]);
  const refreshOutputs = async () => {
    if (refreshing.current || phase !== "stopped" || busy) return;
    refreshing.current = true;
    setError("");
    try {
      const result = await api("audio_outputs");
      const next = Array.isArray(result) ? result : [];
      setOutputs(next);
      if (target !== "auto" && !next.some((output) => output.id === target))
        setTarget("auto");
    } catch (reason) {
      setError(reason.message);
    } finally {
      refreshing.current = false;
    }
  };
  const locked = busy || phase !== "stopped" || !defaults;
  return (
    <Panel title="Audio preview">
      <p className="muted">
        Monitors output audio through PipeWire. No microphone input is used and
        no recording is saved. Rhythm frames can be sent to a connected USB
        keyboard when explicitly enabled.
      </p>
      {(rhythm.mode === "tri-cicle" || rhythm.mode === "triangle") && (
        <p className="muted">
          The rightmost shape is currently inactive. These two modes still need
          validation against the vendor audio stream.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="fields">
        <Field label="Audio output">
          <Select
            aria-label="Audio output"
            value={target}
            disabled={locked}
            options={[
              ["auto", "Automatic output"],
              ...outputs.map((output) => [output.id, output.name]),
            ]}
            onChange={(event) => setTarget(event.target.value)}
          />
        </Field>
        <Field label="Rhythm mode">
          <Select
            value={rhythm.mode}
            disabled={busy}
            options={RHYTHM_MODES}
            onChange={(event) =>
              setRhythm((current) => ({ ...current, mode: event.target.value }))
            }
          />
        </Field>
        <Field label="Rhythm scale">
          <input
            type="number"
            min="0"
            max="100"
            value={rhythm.scale}
            disabled={busy}
            onChange={(event) =>
              setRhythm((current) => ({
                ...current,
                scale: Number(event.target.value),
              }))
            }
          />
        </Field>
        <Field label="Rhythm color mode">
          <Select
            value={rhythm.colorMode}
            disabled={busy}
            options={[
              ["gradient", "Gradient"],
              ["solid", "Solid"],
            ]}
            onChange={(event) =>
              setRhythm((current) => ({
                ...current,
                colorMode: event.target.value,
              }))
            }
          />
        </Field>
        <Field label="Rhythm color">
          <input
            type="color"
            value={rhythm.color}
            disabled={busy}
            onChange={(event) =>
              setRhythm((current) => ({
                ...current,
                color: event.target.value,
              }))
            }
          />
        </Field>
      </div>
      <div className="fields">
        <Field label="Rhythm position X">
          <input
            type="number"
            value={rhythmLayout.x}
            disabled={busy}
            onChange={(event) =>
              updateRhythmLayout((current) =>
                setRhythmPosition(
                  current,
                  Number(event.target.value),
                  current.y,
                ),
              )
            }
          />
        </Field>
        <Field label="Rhythm position Y">
          <input
            type="number"
            value={rhythmLayout.y}
            disabled={busy}
            onChange={(event) =>
              updateRhythmLayout((current) =>
                setRhythmPosition(
                  current,
                  current.x,
                  Number(event.target.value),
                ),
              )
            }
          />
        </Field>
        <Field label="Rhythm width">
          <input
            type="number"
            min="90"
            value={rhythmLayout.width}
            disabled={busy}
            onChange={(event) =>
              updateRhythmLayout((current) =>
                setRhythmSize(
                  current,
                  Number(event.target.value),
                  current.height,
                ),
              )
            }
          />
        </Field>
        <Field label="Rhythm height">
          <input
            type="number"
            min="60"
            value={rhythmLayout.height}
            disabled={busy}
            onChange={(event) =>
              updateRhythmLayout((current) =>
                setRhythmSize(
                  current,
                  current.width,
                  Number(event.target.value),
                ),
              )
            }
          />
        </Field>
        <Field label="Rhythm rotation">
          <input
            type="number"
            min="-180"
            max="180"
            value={rhythmLayout.rotation}
            disabled={busy}
            onChange={(event) =>
              updateRhythmLayout((current) =>
                setRhythmRotation(current, Number(event.target.value)),
              )
            }
          />
        </Field>
      </div>
      <div className="apply-row">
        <Button
          disabled={busy}
          onClick={() =>
            updateRhythmLayout((current) => centerRhythmLayout(current))
          }
        >
          Reset rhythm position
        </Button>
        <Button
          disabled={busy}
          onClick={() => updateRhythmLayout(resetRhythmSize)}
        >
          Reset rhythm size
        </Button>
        <Button
          disabled={busy}
          onClick={() => updateRhythmLayout(resetRhythmRotation)}
        >
          Reset rhythm rotation
        </Button>
        <Button
          disabled={busy}
          onClick={() => updateRhythmLayout(() => defaultRhythmLayout())}
        >
          Reset rhythm layout
        </Button>
      </div>
      <figure aria-label="Rhythm layout preview">
        <svg
          role="img"
          aria-label="Rhythm layout preview"
          viewBox={`0 0 ${RHYTHM_CANVAS.width} ${RHYTHM_CANVAS.height}`}
          width="100%"
          height="180"
          preserveAspectRatio="xMidYMid meet"
        >
          <title>Rhythm layout preview</title>
          <desc>
            A {RHYTHM_CANVAS.width} by {RHYTHM_CANVAS.height} workspace showing
            the sampled rhythm rectangle.
          </desc>
          <rect
            x="0"
            y="0"
            width={RHYTHM_CANVAS.width}
            height={RHYTHM_CANVAS.height}
            fill="#111"
            stroke="currentColor"
          />
          <rect
            x={rhythmLayout.x}
            y={rhythmLayout.y}
            width={rhythmLayout.width}
            height={rhythmLayout.height}
            fill="currentColor"
            fillOpacity="0.25"
            stroke="currentColor"
            transform={`rotate(${rhythmLayout.rotation} ${rhythmLayout.x + rhythmLayout.width / 2} ${rhythmLayout.y + rhythmLayout.height / 2})`}
          />
        </svg>
        <figcaption>
          Workspace {RHYTHM_CANVAS.width}×{RHYTHM_CANVAS.height}; sampling
          rectangle
        </figcaption>
      </figure>
      <label>
        <input
          type="checkbox"
          checked={sendRhythm}
          disabled={!supported || phase !== "stopped" || busy}
          onChange={(event) => setSendRhythm(event.target.checked)}
        />{" "}
        Send rhythm to keyboard
      </label>
      <div className="apply-row">
        <Button disabled={busy || phase !== "stopped"} onClick={refreshOutputs}>
          Refresh audio outputs
        </Button>
        <Button
          disabled={busy || phase !== "stopped" || !defaults}
          onClick={() => setSettings({ ...defaults })}
        >
          Reset audio settings
        </Button>
        <Button
          disabled={busy || phase !== "stopped"}
          onClick={() => setRhythm(RHYTHM_DEFAULTS)}
        >
          Reset rhythm settings
        </Button>
        <Button
          primary
          disabled={busy || phase !== "stopped" || !defaults}
          onClick={start}
        >
          Start audio preview
        </Button>
        <Button
          disabled={phase === "stopped" || phase === "stopping"}
          onClick={() => stopAttempt(attemptRef.current)}
        >
          Stop audio preview
        </Button>
      </div>
      <div className="fields">
        {settingOrder
          .filter((key) => Object.hasOwn(defaults || {}, key))
          .map((key) => {
            const limit = limits[key] || {};
            return (
              <Field key={key} label={labels[key] || key}>
                <input
                  type="number"
                  value={settings[key] ?? ""}
                  min={limit.min}
                  max={limit.max}
                  step={limit.step}
                  disabled={locked}
                  onChange={(event) =>
                    setSettings((current) => ({
                      ...current,
                      [key]: Number(event.target.value),
                    }))
                  }
                />
              </Field>
            );
          })}
      </div>
      <figure aria-label="Audio spectrum preview">
        {bands !== null && (
          <svg
            role="img"
            aria-label="Audio spectrum preview"
            viewBox="0 0 320 100"
            width="100%"
            height="160"
            preserveAspectRatio="none"
          >
            <title>Audio spectrum preview</title>
            <desc>Current output audio levels across 32 frequency bands.</desc>
            {bands.map((value, index) => (
              <rect
                key={index}
                x={index * 10}
                y={100 - Math.max(0, Math.min(1, Number(value) || 0)) * 96}
                width="8"
                height={Math.max(0, Math.min(1, Number(value) || 0)) * 96}
                rx="1"
              />
            ))}
          </svg>
        )}
        {colors && (
          <svg
            role="img"
            aria-label="Rhythm RGB preview"
            viewBox="0 0 21 6"
            width="100%"
            height="120"
          >
            {colors.map((color, index) => (
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
        <figcaption>
          {frameCount} frame{frameCount === 1 ? "" : "s"}
          {sequence === null ? "" : ` · sequence ${sequence}`}
        </figcaption>
      </figure>
    </Panel>
  );
}
