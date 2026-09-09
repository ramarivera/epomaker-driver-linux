import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button } from "./controls";

// Browser KeyboardEvent.code names are physical positions. The values here are
// USB HID keyboard usages, which is also the shape accepted by macros.encode.
const LETTERS = Object.fromEntries(
  Array.from("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (letter, index) => [
    `Key${letter}`,
    4 + index,
  ]),
);
const DIGITS = Object.fromEntries(
  Array.from("1234567890", (digit, index) => [`Digit${digit}`, 30 + index]),
);
const HID_BY_CODE = {
  ...LETTERS,
  ...DIGITS,
  Enter: 40,
  Escape: 41,
  Backspace: 42,
  Tab: 43,
  Space: 44,
  Minus: 45,
  Equal: 46,
  BracketLeft: 47,
  BracketRight: 48,
  Backslash: 49,
  Semicolon: 51,
  Quote: 52,
  Backquote: 53,
  Comma: 54,
  Period: 55,
  Slash: 56,
  CapsLock: 57,
  F1: 58,
  F2: 59,
  F3: 60,
  F4: 61,
  F5: 62,
  F6: 63,
  F7: 64,
  F8: 65,
  F9: 66,
  F10: 67,
  F11: 68,
  F12: 69,
  PrintScreen: 70,
  ScrollLock: 71,
  Pause: 72,
  Insert: 73,
  Home: 74,
  PageUp: 75,
  Delete: 76,
  End: 77,
  PageDown: 78,
  ArrowRight: 79,
  ArrowLeft: 80,
  ArrowDown: 81,
  ArrowUp: 82,
  NumLock: 83,
  NumpadDivide: 84,
  NumpadMultiply: 85,
  NumpadSubtract: 86,
  NumpadAdd: 87,
  NumpadEnter: 88,
  Numpad1: 89,
  Numpad2: 90,
  Numpad3: 91,
  Numpad4: 92,
  Numpad5: 93,
  Numpad6: 94,
  Numpad7: 95,
  Numpad8: 96,
  Numpad9: 97,
  Numpad0: 98,
  NumpadDecimal: 99,
  IntlBackslash: 100,
  ContextMenu: 101,
  F13: 104,
  F14: 105,
  F15: 106,
  F16: 107,
  F17: 108,
  F18: 109,
  F19: 110,
  F20: 111,
  F21: 112,
  F22: 113,
  F23: 114,
  F24: 115,
  ControlLeft: 224,
  ShiftLeft: 225,
  AltLeft: 226,
  MetaLeft: 227,
  ControlRight: 228,
  ShiftRight: 229,
  AltRight: 230,
  MetaRight: 231,
};

const KEY_NAMES = Object.fromEntries(
  Object.entries(HID_BY_CODE).map(([code, usage]) => [
    usage,
    code.replace(/^(Key|Digit)/, "").replace(/([a-z])([A-Z])/g, "$1 $2"),
  ]),
);
const MOUSE_BUTTONS = {
  0: "left",
  1: "middle",
  2: "right",
  3: "back",
  4: "forward",
};
const MOUSE_BUTTON_NAMES = {
  left: "Left mouse button",
  right: "Right mouse button",
  middle: "Middle mouse button",
  back: "Back mouse button",
  forward: "Forward mouse button",
};
export const keyNameForUsage = (usage) => KEY_NAMES[usage] || `HID ${usage}`;
export const mouseButtonName = (button) => MOUSE_BUTTON_NAMES[button] || button;
export const hidUsageForCode = (code) =>
  Object.hasOwn(HID_BY_CODE, code) ? HID_BY_CODE[code] : null;
export const encodedBytes = (events) =>
  2 +
  events.reduce((total, event) => total + (event.delay_ms <= 127 ? 2 : 4), 0);

const MAX_BYTES = 256;
const MIN_DELAY = 1;

export default function MacroRecorder({
  onUse,
  onValidatingChange,
  onPendingChange,
  busy = false,
}) {
  const pad = useRef(null);
  const eventsRef = useRef([]);
  const heldRef = useRef(new Map());
  const lastActionRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [generatedReleases, setGeneratedReleases] = useState(0);
  const [delayMode, setDelayMode] = useState("measured");
  const [fixedDelay, setFixedDelay] = useState(10);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    onPendingChange?.(
      recording || events.length > 0 || Boolean(preview) || validating,
    );
  }, [events.length, onPendingChange, preview, recording, validating]);

  const updateEvents = (next) => {
    eventsRef.current = next;
    setEvents(next);
  };
  const stopWithCleanup = () => {
    const current = eventsRef.current.map((event) => ({
      ...event,
      delay_ms: Math.max(MIN_DELAY, event.delay_ms),
    }));
    if (
      current.length &&
      heldRef.current.size &&
      lastActionRef.current !== null
    ) {
      const delay = Math.round(performance.now() - lastActionRef.current);
      if (delayMode === "measured" && delay > 65535) {
        setError(
          "The pause exceeded the 65535 ms macro delay limit; discard this recording and try again.",
        );
      } else {
        current[current.length - 1].delay_ms =
          delayMode === "fixed" ? fixedDelay : Math.max(MIN_DELAY, delay);
      }
    }
    const releases = [...heldRef.current.values()].reverse().map((held) => ({
      ...held.payload,
      down: false,
      delay_ms: delayMode === "fixed" ? fixedDelay : MIN_DELAY,
    }));
    setGeneratedReleases(releases.length);
    if (releases.length) {
      releases[releases.length - 1].delay_ms =
        delayMode === "fixed" ? fixedDelay : 50;
    } else if (current.length) {
      current[current.length - 1].delay_ms =
        delayMode === "fixed" ? fixedDelay : 50;
    }
    const next = [...current, ...releases];
    if (encodedBytes(next) > MAX_BYTES) {
      setError(
        "Recording is full before held keys could be released; shorten it before using it.",
      );
      updateEvents(current);
    } else {
      updateEvents(next);
    }
    heldRef.current.clear();
    lastActionRef.current = null;
    setRecording(false);
    return next;
  };
  const stop = () => stopWithCleanup();
  const start = () => {
    if (
      delayMode === "fixed" &&
      (!Number.isInteger(fixedDelay) || fixedDelay < 1 || fixedDelay > 65535)
    ) {
      setError("Fixed delay must be an integer from 1 through 65535 ms.");
      return;
    }
    setError("");
    setPreview(null);
    setGeneratedReleases(0);
    heldRef.current.clear();
    lastActionRef.current = performance.now();
    updateEvents([]);
    setRecording(true);
    requestAnimationFrame(() => pad.current?.focus());
  };
  const cancel = () => {
    heldRef.current.clear();
    lastActionRef.current = null;
    setRecording(false);
    setPreview(null);
    setError("");
    setGeneratedReleases(0);
    updateEvents([]);
  };
  const append = (event, now) => {
    const next = eventsRef.current.map((item) => ({ ...item }));
    if (next.length) {
      const delay = Math.round(now - lastActionRef.current);
      if (delayMode === "measured" && delay > 65535) {
        setError(
          "The pause exceeded the 65535 ms macro delay limit; recording stopped.",
        );
        stopWithCleanup();
        return false;
      }
      next[next.length - 1].delay_ms =
        delayMode === "fixed" ? fixedDelay : Math.max(MIN_DELAY, delay);
    }
    next.push(event);
    // Reserve release records and a potentially long measured hold delay.
    const pendingHeld = Math.max(
      0,
      heldRef.current.size + (event.down ? 1 : -1),
    );
    const releaseBytes = delayMode === "fixed" && fixedDelay > 127 ? 4 : 2;
    const reservedCleanup =
      pendingHeld * releaseBytes +
      (pendingHeld && delayMode === "measured" ? 2 : 0);
    if (encodedBytes(next) + reservedCleanup > MAX_BYTES) {
      setError(
        "Recording reached the 256-byte macro capacity. Stop or cancel, then shorten the sequence.",
      );
      stopWithCleanup();
      return false;
    }
    lastActionRef.current = now;
    updateEvents(next);
    return true;
  };
  const handleKey = (event, down) => {
    if (!recording) return;
    if (event.repeat) {
      event.preventDefault();
      return;
    }
    if (event.code === "Escape") {
      event.preventDefault();
      stop();
      return;
    }
    const hid_usage = hidUsageForCode(event.code);
    if (!hid_usage) {
      event.preventDefault();
      setError(
        `Unsupported physical key code “${event.code}”; it was not recorded.`,
      );
      return;
    }
    event.preventDefault();
    if (down) {
      if (heldRef.current.has(`key:${event.code}`)) return;
      if (
        append(
          {
            hid_usage,
            down: true,
            delay_ms: delayMode === "fixed" ? fixedDelay : 50,
          },
          event.timeStamp,
        )
      )
        heldRef.current.set(`key:${event.code}`, { payload: { hid_usage } });
    } else if (heldRef.current.has(`key:${event.code}`)) {
      if (
        append(
          {
            hid_usage,
            down: false,
            delay_ms: delayMode === "fixed" ? fixedDelay : 50,
          },
          event.timeStamp,
        )
      )
        heldRef.current.delete(`key:${event.code}`);
    }
  };
  const handleMouse = (event, down) => {
    if (!recording) return;
    const button = MOUSE_BUTTONS[event.button];
    event.preventDefault();
    if (!button) {
      setError(
        `Unsupported mouse button “${event.button}”; it was not recorded.`,
      );
      return;
    }
    const heldKey = `mouse:${button}`;
    if (down) {
      if (heldRef.current.has(heldKey)) return;
      if (
        append(
          {
            type: "mouse_button",
            button,
            down: true,
            delay_ms: delayMode === "fixed" ? fixedDelay : 50,
          },
          event.timeStamp,
        )
      )
        heldRef.current.set(heldKey, {
          payload: { type: "mouse_button", button },
        });
    } else if (heldRef.current.has(heldKey)) {
      if (
        append(
          {
            type: "mouse_button",
            button,
            down: false,
            delay_ms: delayMode === "fixed" ? fixedDelay : 50,
          },
          event.timeStamp,
        )
      )
        heldRef.current.delete(heldKey);
    }
  };
  useEffect(() => {
    if (!recording) return undefined;
    const releaseOutsidePad = (event) => {
      const button = MOUSE_BUTTONS[event.button];
      if (button && heldRef.current.has(`mouse:${button}`))
        handleMouse(event, false);
    };
    window.addEventListener("mouseup", releaseOutsidePad, true);
    return () => window.removeEventListener("mouseup", releaseOutsidePad, true);
  }, [recording]);
  const useDraft = async () => {
    if (
      busy ||
      validating ||
      !preview ||
      heldRef.current.size ||
      encodedBytes(preview.events) > MAX_BYTES
    )
      return;
    setValidating(true);
    onValidatingChange(true);
    try {
      const valid = await api("validate_macro", { value: preview });
      onUse(valid);
      setPreview(null);
      setError("");
      updateEvents([]);
    } catch (validationError) {
      setError(validationError.message);
    } finally {
      setValidating(false);
      onValidatingChange(false);
    }
  };
  return (
    <div className="macro-recorder">
      <h3>Record input sequence</h3>
      <p className="muted">
        App-local capture only. Browser and OS-reserved shortcuts may be
        unavailable.
      </p>
      <p className="muted">
        Type or click here to record keys and mouse buttons: left, right,
        middle, back and forward. Escape stops recording; releases outside this
        area are tracked for buttons already held here.
      </p>
      <p className="muted">
        Movement and scrolling are not recorded. Add movement or Escape events
        in the editor when needed.
      </p>
      <div className="fields compact">
        <label>
          Delay mode
          <select
            aria-label="Recording delay mode"
            disabled={recording || validating || busy}
            value={delayMode}
            onChange={(event) => setDelayMode(event.target.value)}
          >
            <option value="measured">Measured timing</option>
            <option value="fixed">Fixed delay</option>
          </select>
        </label>
        {delayMode === "fixed" && (
          <label>
            Delay (ms)
            <input
              aria-label="Fixed recording delay"
              type="number"
              min="1"
              max="65535"
              disabled={recording || validating || busy}
              value={fixedDelay}
              onChange={(event) => setFixedDelay(Number(event.target.value))}
            />
          </label>
        )}
      </div>
      <div
        ref={pad}
        className={`macro-capture-pad${recording ? " recording" : ""}`}
        tabIndex={0}
        role="textbox"
        aria-label="Recording area"
        aria-readonly="true"
        onKeyDown={(event) => handleKey(event, true)}
        onKeyUp={(event) => handleKey(event, false)}
        onMouseDown={(event) => handleMouse(event, true)}
        onMouseUp={(event) => handleMouse(event, false)}
        onContextMenu={(event) => recording && event.preventDefault()}
        onAuxClick={(event) => recording && event.preventDefault()}
        onBlur={() => recording && stop()}
      >
        {recording
          ? "Recording… type or click here, then stop"
          : "Focus here to capture keyboard or mouse input"}
      </div>
      <div className="apply-row">
        {!recording ? (
          <Button disabled={busy || validating} onClick={start}>
            Start recording
          </Button>
        ) : (
          <Button
            primary
            disabled={busy}
            onPointerDown={(event) => event.preventDefault()}
            onClick={stop}
          >
            Stop recording
          </Button>
        )}
        {recording && (
          <Button
            disabled={busy || validating}
            onPointerDown={(event) => event.preventDefault()}
            onClick={cancel}
          >
            Cancel
          </Button>
        )}
      </div>
      {generatedReleases > 0 && (
        <p role="note">
          Added {generatedReleases} release{" "}
          {generatedReleases === 1 ? "action" : "actions"} for held keys. Review
          them before using this recording.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!recording && events.length > 0 && !preview && (
        <div className="macro-preview">
          <strong>
            Recorded {events.length} actions ({encodedBytes(events)}/256 bytes)
          </strong>
          <p className="muted">
            Review the sequence before replacing the editor.
          </p>
          <div className="apply-row">
            <Button
              primary
              disabled={busy || Boolean(error)}
              onClick={() => setPreview({ repeat: 1, events })}
            >
              Use recording
            </Button>
            <Button onClick={cancel}>Discard recording</Button>
          </div>
        </div>
      )}
      {preview && (
        <div className="macro-preview">
          <strong>Preview: {preview.events.length} actions</strong>
          <ol>
            {preview.events.map((event, index) => (
              <li key={index}>
                {event.down ? "Press" : "Release"}{" "}
                {event.type === "mouse_button"
                  ? MOUSE_BUTTON_NAMES[event.button]
                  : KEY_NAMES[event.hid_usage]}{" "}
                · {event.delay_ms} ms
              </li>
            ))}
          </ol>
          <div className="apply-row">
            <Button primary disabled={validating || busy} onClick={useDraft}>
              {validating ? "Validating…" : "Replace editor with recording"}
            </Button>
            <Button disabled={validating} onClick={() => setPreview(null)}>
              Back
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
