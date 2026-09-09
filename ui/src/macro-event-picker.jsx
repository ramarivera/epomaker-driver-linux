import React, { useEffect, useRef, useState } from "react";
import { Button } from "./controls";
import {
  hidUsageForCode,
  keyNameForUsage,
  mouseButtonName,
} from "./macro-recorder";

const BUTTONS = { 0: "left", 1: "middle", 2: "right", 3: "back", 4: "forward" };

export default function MacroEventPicker({
  eventIndex,
  pair = false,
  onApply,
  onCancel,
}) {
  const picker = useRef(null);
  const surface = useRef(null);
  const [candidate, setCandidate] = useState(null);
  const [error, setError] = useState("");
  const [applying, setApplying] = useState(false);
  const [pairDelay, setPairDelay] = useState(50);
  useEffect(() => surface.current?.focus(), []);
  const cancel = () => {
    if (!applying) onCancel();
  };
  const captureKey = (event) => {
    if (applying) return;
    if (event.code === "Tab" && candidate) return;
    if (event.repeat) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    if (event.code === "Escape") {
      cancel();
      return;
    }
    const hid_usage = hidUsageForCode(event.code);
    if (!hid_usage) {
      setCandidate(null);
      setError(
        `Unsupported physical key code “${event.code}”; try another key.`,
      );
      return;
    }
    setError("");
    setCandidate({
      type: "keyboard",
      hid_usage,
      label: keyNameForUsage(hid_usage),
    });
  };
  const captureMouse = (event) => {
    if (applying) return;
    event.preventDefault();
    const button = BUTTONS[event.button];
    if (!button) {
      setCandidate(null);
      setError(
        `Unsupported mouse button “${event.button}”; try another button.`,
      );
      return;
    }
    setError("");
    setCandidate({
      type: "mouse_button",
      button,
      label: mouseButtonName(button),
    });
  };
  const apply = async () => {
    if (!candidate || applying) return;
    if (
      pair &&
      (!Number.isInteger(pairDelay) || pairDelay < 1 || pairDelay > 65535)
    ) {
      setError("Pair delay must be an integer from 1 through 65535 ms.");
      return;
    }
    setApplying(true);
    try {
      await onApply({ ...candidate, delay_ms: pairDelay });
    } catch (applyError) {
      setError(applyError.message);
      setApplying(false);
    }
  };
  return (
    <div
      ref={picker}
      className="macro-event-picker"
      role="dialog"
      aria-label={`Capture event ${eventIndex}`}
      onKeyDown={(event) => {
        if (event.code === "Escape") cancel();
      }}
    >
      <strong>
        {pair ? "Capture key/button pair" : `Capture event ${eventIndex}`}
      </strong>
      <p className="muted">
        Press a key or click a mouse button in the capture area. Escape or
        leaving the picker cancels. Browser and OS-reserved shortcuts may be
        unavailable.
      </p>
      {pair && (
        <label>
          Pair delay (ms)
          <input
            aria-label="Pair delay"
            type="number"
            min="1"
            max="65535"
            value={pairDelay}
            disabled={applying}
            onChange={(event) => setPairDelay(Number(event.target.value))}
          />
        </label>
      )}
      <div
        ref={surface}
        className="macro-capture-pad macro-picker-surface"
        tabIndex={0}
        role="textbox"
        aria-label="Event capture area"
        aria-readonly="true"
        aria-live="polite"
        onKeyDown={captureKey}
        onMouseDown={captureMouse}
        onContextMenu={(event) => event.preventDefault()}
        onAuxClick={(event) => event.preventDefault()}
        onBlur={
          pair
            ? undefined
            : (event) => {
                if (!picker.current?.contains(event.relatedTarget)) cancel();
              }
        }
      >
        {candidate
          ? `Preview: ${candidate.label}`
          : "Press a key or click a mouse button"}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="apply-row">
        <Button
          primary
          disabled={!candidate || applying}
          onPointerDown={(event) => event.preventDefault()}
          onClick={apply}
        >
          {applying
            ? "Validating…"
            : pair
              ? "Apply pair"
              : "Apply captured input"}
        </Button>
        <Button
          disabled={applying}
          onPointerDown={(event) => event.preventDefault()}
          onClick={cancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
