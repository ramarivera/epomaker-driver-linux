import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel, Select } from "./controls";

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

export default function AudioPreview({ busy = false }) {
  const [defaults, setDefaults] = useState(null);
  const [limits, setLimits] = useState({});
  const [settings, setSettings] = useState({});
  const [outputs, setOutputs] = useState([]);
  const [target, setTarget] = useState("auto");
  const [bands, setBands] = useState(null);
  const [sequence, setSequence] = useState(null);
  const [frameCount, setFrameCount] = useState(0);
  const [phase, setPhase] = useState("stopped");
  const [error, setError] = useState("");
  const mounted = useRef(true);
  const generation = useRef(0);
  const attemptRef = useRef(null);
  const starting = useRef(false);
  const refreshing = useRef(false);

  useEffect(() => {
    let active = true;
    api("audio_config")
      .then((result) => {
        if (!active || !mounted.current) return;
        const nextDefaults = result.defaults || {};
        setDefaults(nextDefaults);
        setSettings({ ...nextDefaults });
        setLimits(result.limits || {});
      })
      .catch((reason) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const stopAttempt = useCallback(
    async (attempt, reason = "") => {
      if (!attempt || attempt.stopped) return;
      attempt.stopped = true;
      if (attempt.timer !== null) clearTimeout(attempt.timer);
      const wasCurrent = attemptRef.current === attempt;
      if (wasCurrent) {
        attemptRef.current = null;
        starting.current = false;
      }
      const current =
        attemptRef.current === null || attemptRef.current === attempt;
      if (current && mounted.current) {
        // Release the controls immediately; cleanup remains serialized below.
        // A new generation prevents this cleanup's result from touching it.
        setPhase("stopped");
        setBands(null);
        setSequence(null);
      }
      let cleanupError = "";
      if (attempt.session) {
        try {
          const result = await api("audio_preview_stop", {
            session: attempt.session,
          });
          if (result?.ok === false)
            cleanupError = result.error || "Could not stop audio preview.";
          else if (result?.error) cleanupError = result.error;
        } catch (stopError) {
          cleanupError = stopError.message;
        }
      }
      if (!mounted.current || generation.current !== attempt.generation) return;
      setPhase("stopped");
      setBands(null);
      setSequence(null);
      if (cleanupError)
        setError(`Audio preview cleanup failed: ${cleanupError}`);
      else if (reason) setError(reason);
    },
    [defaults],
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
        if (sample.error) {
          await stopAttempt(attempt, sample.error);
          return;
        }
        if (sample.running === false) {
          await stopAttempt(attempt);
          return;
        }
        setBands(Array.isArray(sample.bands) ? sample.bands : null);
        setSequence(sample.sequence ?? null);
        setFrameCount((count) => count + 1);
        attempt.timer = setTimeout(() => poll(attempt), 100);
      } catch (pollError) {
        if (attempt.stopped || attemptRef.current !== attempt) return;
        await stopAttempt(attempt, pollError.message);
      }
    },
    [stopAttempt],
  );

  const start = async () => {
    if (starting.current || phase !== "stopped" || !defaults) return;
    starting.current = true;
    const attempt = {
      generation: ++generation.current,
      session: null,
      timer: null,
      stopped: false,
    };
    attemptRef.current = attempt;
    setPhase("starting");
    setError("");
    setBands(null);
    setSequence(null);
    setFrameCount(0);
    try {
      const result = await api("audio_preview_start", { target, settings });
      attempt.session = result.session;
      if (
        !mounted.current ||
        generation.current !== attempt.generation ||
        attemptRef.current !== attempt
      ) {
        if (attempt.session) {
          try {
            await api("audio_preview_stop", { session: attempt.session });
          } catch {
            // The attempt was cancelled or the page is leaving.
          }
        }
        return;
      }
      setPhase("running");
      await poll(attempt);
    } catch (startError) {
      if (
        mounted.current &&
        generation.current === attempt.generation &&
        attemptRef.current === attempt
      )
        await stopAttempt(attempt, startError.message);
      else if (attempt.session) {
        try {
          await api("audio_preview_stop", { session: attempt.session });
        } catch {
          // The page is already leaving; there is no state left to report.
        }
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
      if (attempt?.session)
        void api("audio_preview_stop", { session: attempt.session }).catch(
          () => {},
        );
      if (attempt && attempt.timer !== null) clearTimeout(attempt.timer);
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

  const refreshOutputs = async () => {
    if (refreshing.current || phase !== "stopped" || busy) return;
    refreshing.current = true;
    setError("");
    try {
      const result = await api("audio_outputs");
      const nextOutputs = Array.isArray(result) ? result : [];
      setOutputs(nextOutputs);
      if (
        target !== "auto" &&
        !nextOutputs.some((output) => output.id === target)
      )
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
        Monitors output audio through PipeWire. No microphone input is used, no
        recording is saved, and this preview currently does not control the
        keyboard.
      </p>
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
      </div>
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
            <title id="audio-preview-title">Audio spectrum preview</title>
            <desc id="audio-preview-description">
              Current output audio levels across 32 frequency bands.
            </desc>
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
        <figcaption>
          {frameCount} frame{frameCount === 1 ? "" : "s"}
          {sequence === null ? "" : ` · sequence ${sequence}`}
        </figcaption>
      </figure>
    </Panel>
  );
}
