import React, { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Panel } from "./controls";

export default function ScreenErase({
  connected,
  identity,
  busy,
  run,
  status,
  onStatus,
  onAcknowledged,
}) {
  const [confirm, setConfirm] = useState(false);
  const [ackConfirm, setAckConfirm] = useState(false);
  useEffect(() => {
    setConfirm(false);
    setAckConfirm(false);
  }, [identity?.session, status?.operation_id]);
  const start = () => {
    setConfirm(false);
    run(async () => {
      try {
        const next = await api("screen_erase_start", {
          session: identity.session,
          confirm: true,
        });
        onStatus(next);
      } catch (error) {
        await onStatus();
        throw error;
      }
    });
  };
  const acknowledge = () => {
    run(async () => {
      const next = await api("screen_erase_acknowledge", {
        operation_id: status.operation_id,
        confirm: true,
      });
      setAckConfirm(false);
      onAcknowledged(next);
    });
  };
  return (
    <Panel title="Clear keyboard screen">
      <p className="muted">
        This clears screen storage. Local image drafts and the asset library are
        retained.
      </p>
      {status?.state === "uncertain" && (
        <p role="alert">
          The erase outcome is unknown. Check the keyboard before acknowledging;
          it will not be retried automatically.
        </p>
      )}
      {status?.state === "uncertain" && (
        <label>
          <input
            type="checkbox"
            checked={ackConfirm}
            onChange={(e) => setAckConfirm(e.target.checked)}
          />{" "}
          I have checked the keyboard and understand the erase outcome may be
          unknown.
        </label>
      )}
      {status?.state === "uncertain" ? (
        <Button disabled={busy || !ackConfirm} onClick={acknowledge}>
          Acknowledge outcome
        </Button>
      ) : (
        <>
          <label>
            <input
              type="checkbox"
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
            />{" "}
            I understand this erases keyboard screen storage; screen pixels
            cannot be backed up.
          </label>
          <Button
            primary
            disabled={!connected || busy || !confirm || status?.blocked}
            onClick={start}
          >
            Clear keyboard screen
          </Button>
        </>
      )}
    </Panel>
  );
}
