import React, { useEffect, useRef, useState } from "react";
import { Button, Field, Select } from "./controls";

// Pixel geometry and history: docs/releases/glyph-display-paint-audit.md.
export default function DisplayPaint({ png, busy, onApply, onCancel }) {
  const dialog = useRef(null),
    canvas = useRef(null),
    viewport = useRef(null);
  const stroke = useRef(null),
    history = useRef({ past: [], future: [] });
  const space = useRef(false);
  const [ready, setReady] = useState(false),
    [drawing, setDrawing] = useState(false);
  const [tool, setTool] = useState("brush"),
    [color, setColor] = useState("#ffffff");
  const [size, setSize] = useState(1),
    [zoom, setZoom] = useState(1);
  const [revision, setRevision] = useState(0),
    [error, setError] = useState("");
  useEffect(() => {
    const modal = dialog.current;
    modal.showModal();
    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;
      canvas.current
        .getContext("2d", { willReadFrequently: true })
        .drawImage(image, 0, 0);
      setReady(true);
    };
    image.onerror = () => {
      if (!cancelled) setError("Could not load this frame.");
    };
    image.src = `data:image/png;base64,${png}`;
    return () => {
      cancelled = true;
      modal.close();
    };
  }, [png]);
  useEffect(() => {
    const view = viewport.current;
    const wheel = (event) => {
      event.preventDefault();
      if (!busy && !stroke.current)
        setZoom((value) =>
          Math.max(1, Math.min(5, value + (event.deltaY < 0 ? 1 : -1))),
        );
    };
    view.addEventListener("wheel", wheel, { passive: false });
    return () => view.removeEventListener("wheel", wheel);
  }, [busy]);
  const context = () =>
    canvas.current.getContext("2d", { willReadFrequently: true });
  const snapshot = () => context().getImageData(0, 0, 428, 142);
  const point = (event) => {
    const box = canvas.current.getBoundingClientRect();
    return [
      Math.max(
        0,
        Math.min(
          427,
          Math.floor(((event.clientX - box.left) * 428) / box.width),
        ),
      ),
      Math.max(
        0,
        Math.min(
          141,
          Math.floor(((event.clientY - box.top) * 142) / box.height),
        ),
      ),
    ];
  };
  const paint = (from, to) => {
    const ctx = context();
    ctx.fillStyle = tool === "eraser" ? "#000000" : color;
    const steps = Math.max(
      Math.abs(to[0] - from[0]),
      Math.abs(to[1] - from[1]),
    );
    for (let step = 0; step <= steps; step++) {
      const fraction = steps === 0 ? 0 : step / steps;
      const x = Math.round(from[0] + (to[0] - from[0]) * fraction);
      const y = Math.round(from[1] + (to[1] - from[1]) * fraction);
      ctx.fillRect(x - (size - 1) / 2, y - (size - 1) / 2, size, size);
    }
  };
  const stopStroke = (cancelled) => {
    if (!stroke.current) return;
    if (!stroke.current.pan) {
      if (cancelled) context().putImageData(stroke.current.before, 0, 0);
      else {
        history.current.past = [
          ...history.current.past,
          stroke.current.before,
        ].slice(-10);
        history.current.future = [];
        setRevision((value) => value + 1);
      }
    }
    stroke.current = null;
    setDrawing(false);
  };
  const restore = (direction) => {
    const source = history.current[direction];
    if (busy || drawing || !source.length) return;
    const target = direction === "past" ? "future" : "past";
    history.current[target] = [...history.current[target], snapshot()].slice(
      -10,
    );
    context().putImageData(source.pop(), 0, 0);
    setRevision((value) => value + 1);
  };
  const locked = busy || drawing || !ready;
  return (
    <dialog
      ref={dialog}
      className="display-paint-dialog"
      aria-label="Paint display frame"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2>Paint display frame</h2>
      <div className="fields">
        <Field label="Paint tool">
          <Select
            value={tool}
            disabled={locked}
            options={[
              ["brush", "Brush"],
              ["eraser", "Eraser"],
            ]}
            onChange={(event) => setTool(event.target.value)}
          />
        </Field>
        <Field label="Paint color">
          <input
            type="color"
            value={color}
            disabled={locked}
            onChange={(event) => setColor(event.target.value)}
          />
        </Field>
        <Field label="Brush width">
          <Select
            value={size}
            disabled={locked}
            options={[
              [1, "1 pixel"],
              [3, "3 pixels"],
              [5, "5 pixels"],
            ]}
            onChange={(event) => setSize(Number(event.target.value))}
          />
        </Field>
        <Field label="Canvas zoom">
          <Select
            value={zoom}
            disabled={locked}
            options={[1, 2, 3, 4, 5].map((value) => [value, `${value}×`])}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
        </Field>
        <Button
          disabled={locked}
          onClick={() => {
            setZoom(1);
            viewport.current.scrollTo(0, 0);
          }}
        >
          Reset canvas view
        </Button>
      </div>
      <p>
        Paint with the pointer. Wheel to zoom; hold Space and drag to pan.
        Changes stay here until you apply them to the draft.
      </p>
      <div className="display-paint-viewport" ref={viewport}>
        <canvas
          ref={canvas}
          width={428}
          height={142}
          tabIndex={0}
          role="img"
          aria-label="Frame painting canvas"
          style={{ width: `${856 * zoom}px`, height: `${284 * zoom}px` }}
          onKeyDown={(event) => {
            if (event.code === "Space") {
              event.preventDefault();
              space.current = true;
            }
          }}
          onKeyUp={(event) => {
            if (event.code === "Space") {
              event.preventDefault();
              space.current = false;
            }
          }}
          onBlur={() => {
            space.current = false;
            stopStroke(true);
          }}
          onPointerDown={(event) => {
            if (busy || !ready || event.button !== 0 || stroke.current) return;
            event.preventDefault();
            event.currentTarget.focus();
            event.currentTarget.setPointerCapture(event.pointerId);
            setDrawing(true);
            if (space.current)
              stroke.current = {
                pan: true,
                x: event.clientX,
                y: event.clientY,
                left: viewport.current.scrollLeft,
                top: viewport.current.scrollTop,
              };
            else {
              const p = point(event);
              stroke.current = { before: snapshot(), last: p };
              paint(p, p);
            }
          }}
          onPointerMove={(event) => {
            const active = stroke.current;
            if (!active || busy) return;
            if (active.pan) {
              viewport.current.scrollLeft =
                active.left - (event.clientX - active.x);
              viewport.current.scrollTop =
                active.top - (event.clientY - active.y);
            } else {
              const p = point(event);
              paint(active.last, p);
              active.last = p;
            }
          }}
          onPointerUp={() => stopStroke(false)}
          onPointerCancel={() => stopStroke(true)}
          onLostPointerCapture={() => stopStroke(true)}
        />
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="fields" data-revision={revision}>
        <Button
          disabled={locked || !history.current.past.length}
          onClick={() => restore("past")}
        >
          Undo stroke
        </Button>
        <Button
          disabled={locked || !history.current.future.length}
          onClick={() => restore("future")}
        >
          Redo stroke
        </Button>
        <Button
          disabled={locked}
          primary
          onClick={async () => {
            setError("");
            const success = await onApply(
              canvas.current.toDataURL("image/png").split(",")[1],
            );
            if (!success)
              setError(
                "Could not apply the drawing. It is retained here; try again or cancel.",
              );
          }}
        >
          Apply painting to draft
        </Button>
        <Button disabled={busy} onClick={onCancel}>
          Cancel painting
        </Button>
      </div>
    </dialog>
  );
}
