import React, { useEffect, useRef, useState } from "react";
import { Button, Field, Select } from "./controls";

// Vendor placement semantics: docs/releases/glyph-display-import-audit.md.
const formatCoordinate = (value) => String(Number(value.toFixed(6)));
const clampScale = (value) => Math.max(20, Math.min(300, value));

export default function DisplayImport({
  file,
  metadata,
  busy,
  onApply,
  onCancel,
}) {
  const dialog = useRef(null);
  const viewport = useRef(null);
  const drag = useRef(null);
  const [source, setSource] = useState("");
  const [scale, setScale] = useState(100);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [positionInput, setPositionInput] = useState({ x: "0", y: "0" });
  const [error, setError] = useState("");
  const [applying, setApplying] = useState(false);
  const [ready, setReady] = useState(false);
  const fitWidth = Number(metadata?.fit_width) || 428;
  const fitHeight = Number(metadata?.fit_height) || 142;
  const initial = {
    x: Number(metadata?.initial_x) || 0,
    y: Number(metadata?.initial_y) || 0,
  };
  const locked = busy || applying;

  useEffect(() => {
    const modal = dialog.current;
    modal?.showModal();
    const url = file ? URL.createObjectURL(file) : "";
    setSource(url);
    setScale(100);
    setPosition(initial);
    setPositionInput({
      x: formatCoordinate(initial.x),
      y: formatCoordinate(initial.y),
    });
    setError("");
    setReady(false);
    return () => {
      if (url) URL.revokeObjectURL(url);
      modal?.close();
    };
  }, [file, metadata]);

  useEffect(() => {
    const view = viewport.current;
    if (!view) return undefined;
    const wheel = (event) => {
      if (locked) return;
      event.preventDefault();
      changeScale(scale + (event.deltaY < 0 ? 20 : -20));
    };
    view.addEventListener("wheel", wheel, { passive: false });
    return () => view.removeEventListener("wheel", wheel);
  }, [locked, scale]);

  const recenter = (nextScale) => {
    const next = {
      x: (428 - fitWidth * (nextScale / 100)) / 2,
      y: (142 - fitHeight * (nextScale / 100)) / 2,
    };
    setPosition(next);
    setPositionInput({
      x: formatCoordinate(next.x),
      y: formatCoordinate(next.y),
    });
  };

  const changeScale = (value) => {
    const next = clampScale(value);
    setScale(next);
    recenter(next);
  };

  const updatePosition = (axis, value) => {
    setPositionInput((current) => ({ ...current, [axis]: value }));
    if (value.trim() === "") {
      setError(`${axis === "x" ? "Position X" : "Position Y"} is required.`);
      return;
    }
    const next = Number(value);
    if (!Number.isFinite(next)) {
      setError(`${axis === "x" ? "Position X" : "Position Y"} must be finite.`);
      return;
    }
    setError("");
    setPosition((current) => ({ ...current, [axis]: next }));
  };

  const finishApply = async () => {
    if (locked) return;
    const x = Number(positionInput.x);
    const y = Number(positionInput.y);
    if (
      positionInput.x.trim() === "" ||
      positionInput.y.trim() === "" ||
      !Number.isFinite(x) ||
      !Number.isFinite(y)
    ) {
      setError("Image position must be finite.");
      return;
    }
    setError("");
    setApplying(true);
    try {
      const accepted = await onApply({ scale, x, y });
      if (accepted === true) dialog.current?.close();
      else setError("Image import was not accepted.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setApplying(false);
    }
  };

  return (
    <dialog
      ref={dialog}
      className="display-import-dialog"
      aria-label="Prepare display image"
      onCancel={(event) => {
        event.preventDefault();
        if (!locked) onCancel();
      }}
    >
      <h2>Prepare display image</h2>
      <p>
        Adjust the image before importing it into the display frame.{" "}
        {metadata?.replace_all
          ? "This animation/GIF import replaces all prepared frames."
          : "This still image replaces the current frame."}
      </p>
      <div
        className="display-import-viewport"
        ref={viewport}
        onPointerDown={(event) => {
          if (
            locked ||
            event.button !== 0 ||
            drag.current ||
            !Number.isFinite(Number(positionInput.x)) ||
            !Number.isFinite(Number(positionInput.y))
          )
            return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            position,
          };
        }}
        onPointerMove={(event) => {
          const active = drag.current;
          if (!active || locked) return;
          const box = viewport.current.getBoundingClientRect();
          setPosition({
            x:
              active.position.x +
              ((event.clientX - active.startX) * 428) / box.width,
            y:
              active.position.y +
              ((event.clientY - active.startY) * 142) / box.height,
          });
          setPositionInput({
            x: formatCoordinate(
              active.position.x +
                ((event.clientX - active.startX) * 428) / box.width,
            ),
            y: formatCoordinate(
              active.position.y +
                ((event.clientY - active.startY) * 142) / box.height,
            ),
          });
        }}
        onPointerUp={(event) => {
          if (drag.current?.pointerId === event.pointerId) drag.current = null;
        }}
        onPointerCancel={() => {
          if (drag.current) {
            setPosition(drag.current.position);
            setPositionInput({
              x: formatCoordinate(drag.current.position.x),
              y: formatCoordinate(drag.current.position.y),
            });
          }
          drag.current = null;
        }}
        onLostPointerCapture={() => {
          if (drag.current) {
            setPosition(drag.current.position);
            setPositionInput({
              x: formatCoordinate(drag.current.position.x),
              y: formatCoordinate(drag.current.position.y),
            });
          }
          drag.current = null;
        }}
      >
        {source && (
          <img
            className="display-import-image"
            src={source}
            alt="Image import preview"
            draggable="false"
            onLoad={() => setReady(true)}
            onError={() => {
              setReady(false);
              setError("Could not decode this image.");
            }}
            style={{
              left: `${(position.x / 428) * 100}%`,
              top: `${(position.y / 142) * 100}%`,
              width: `${(fitWidth * (scale / 100) * 100) / 428}%`,
              height: `${(fitHeight * (scale / 100) * 100) / 142}%`,
            }}
          />
        )}
      </div>
      <div className="display-import-controls fields">
        <Field label="Scale">
          <Select
            value={scale}
            disabled={locked}
            options={Array.from({ length: 15 }, (_, index) => [
              (index + 1) * 20,
              `${(index + 1) * 20}%`,
            ])}
            onChange={(event) => changeScale(Number(event.target.value))}
          />
        </Field>
        <Field label="Position X">
          <input
            type="number"
            step="any"
            value={positionInput.x}
            disabled={locked}
            onChange={(event) => updatePosition("x", event.target.value)}
          />
        </Field>
        <Field label="Position Y">
          <input
            type="number"
            step="any"
            value={positionInput.y}
            disabled={locked}
            onChange={(event) => updatePosition("y", event.target.value)}
          />
        </Field>
      </div>
      <p className="muted">
        Use the wheel to scale or drag the image to reposition it.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="apply-row">
        <Button disabled={locked} onClick={onCancel}>
          Cancel
        </Button>
        <Button
          primary
          disabled={
            locked ||
            !ready ||
            !source ||
            positionInput.x.trim() === "" ||
            positionInput.y.trim() === "" ||
            !Number.isFinite(Number(positionInput.x)) ||
            !Number.isFinite(Number(positionInput.y))
          }
          onClick={finishApply}
        >
          Apply image
        </Button>
      </div>
    </dialog>
  );
}
