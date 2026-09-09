import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button, Field, Panel } from "./controls";

export default function SystemInfoRefresh({ connected, busy, run }) {
  const [status, setStatus] = useState(null),
    [error, setError] = useState("");
  const [interval, setIntervalValue] = useState("2"),
    [disk, setDisk] = useState("/"),
    [network, setNetwork] = useState("");
  const [pollError, setPollError] = useState("");
  const generation = useRef(0);
  useEffect(() => {
    let disposed = false,
      pending = false,
      initialized = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      const current = generation.current;
      try {
        const value = await api("system_info_refresh");
        if (!disposed && current === generation.current) {
          setStatus(value);
          setPollError("");
          if (!initialized) {
            setIntervalValue(String(value.interval ?? 2));
            setDisk(value.disk ?? "/");
            setNetwork(value.interface ?? "");
            initialized = true;
          }
        }
      } catch (err) {
        if (!disposed && current === generation.current)
          setPollError(err.message);
      } finally {
        pending = false;
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, []);
  const change = (operation, data) => {
    generation.current++;
    run(async () => {
      setError("");
      try {
        setStatus(await api(operation, data));
      } catch (err) {
        setError(err.message);
      } finally {
        generation.current++;
      }
    });
  };
  const running = Boolean(status?.running);
  const locked = busy || running || !status;
  return (
    <Panel title="Continuous system information">
      <p className="muted">
        Refresh the keyboard’s system-information display while this server
        runs, including when you switch pages or close the browser.
        Disconnecting or stopping the server ends refresh.
      </p>
      {error && <p role="alert">{error}</p>}
      {pollError && <p role="alert">Status refresh failed: {pollError}</p>}
      {status?.error && <p role="alert">Refresh stopped: {status.error}</p>}
      <p role="status">
        {running
          ? "System information refresh running"
          : "System information refresh stopped"}{" "}
        · {status?.samples ?? 0} samples sent
      </p>
      <div className="fields">
        <Field label="Refresh interval (seconds)">
          <input
            type="number"
            min="1"
            max="3600"
            step="1"
            value={interval}
            disabled={locked}
            onChange={(e) => setIntervalValue(e.target.value)}
          />
        </Field>
        <Field label="Disk path">
          <input
            value={disk}
            disabled={locked}
            onChange={(e) => setDisk(e.target.value)}
          />
        </Field>
        <Field label="Network interface (optional)">
          <input
            value={network}
            disabled={locked}
            placeholder="Automatic"
            onChange={(e) => setNetwork(e.target.value)}
          />
        </Field>
      </div>
      <div className="apply-row">
        <Button
          disabled={busy || !connected || running || !status}
          onClick={() => {
            const seconds = Number(interval);
            if (
              !Number.isFinite(seconds) ||
              seconds < 1 ||
              seconds > 3600 ||
              !disk.trim()
            ) {
              setError(
                "Choose an interval from 1 to 3600 seconds and a disk path.",
              );
              return;
            }
            change("system_info_refresh_start", {
              interval: seconds,
              disk: disk.trim(),
              interface: network.trim() || null,
            });
          }}
        >
          Start system information refresh
        </Button>
        <Button
          disabled={busy || !running}
          onClick={() => change("system_info_refresh_stop", {})}
        >
          Stop system information refresh
        </Button>
      </div>
      {status?.last_sample && (
        <div>
          <p>
            Last sample: CPU {status.last_sample.cpu_usage}% · Temperature{" "}
            {status.last_sample.cpu_temperature ?? "unavailable"}
            {status.last_sample.cpu_temperature == null ? "" : " °C"} ·
            Interface {status.last_sample.interface ?? "unavailable"}
          </p>
          {status.last_sample.warnings?.map((warning, i) => (
            <p className="muted" key={i}>
              {warning}
            </p>
          ))}
        </div>
      )}
    </Panel>
  );
}
