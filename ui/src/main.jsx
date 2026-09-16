import React, { useCallback, useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  Keyboard,
  Lightbulb,
  Play,
  Monitor,
  Settings as SettingsIcon,
  Database,
  LoaderCircle,
} from "lucide-react";
import { api } from "./api";
import { Button, Select } from "./controls";
import Keymap from "./keymap";
import Lighting from "./lighting";
import { DEFAULT_RATIO } from "./live-light-crop";
import MacrosEditor from "./macros-editor";
import Display from "./display";
import Settings from "./settings";
import Backups from "./backups";
import ConnectionTelemetry from "./connection-telemetry";
import "./style.css";
const pages = [
  ["Keymap", Keyboard, Keymap, "Select a key to change its assignment."],
  ["Lighting", Lightbulb, Lighting, "Set effects and paint custom colors."],
  [
    "Macros",
    Play,
    MacrosEditor,
    "Create and assign keyboard and mouse sequences.",
  ],
  [
    "Display",
    Monitor,
    Display,
    "Choose images and information for your keyboard.",
  ],
  ["Settings", SettingsIcon, Settings, "Read and update keyboard preferences."],
  [
    "Backups",
    Database,
    Backups,
    "Save your configuration and restore it with a recovery copy.",
  ],
];
function App() {
  const [screenRatio, setScreenRatio] = useState(DEFAULT_RATIO);
  const [tab, setTab] = useState("Keymap"),
    [catalog, setCatalog] = useState(null),
    [devices, setDevices] = useState([]),
    [path, setPath] = useState(""),
    [identity, setIdentity] = useState(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(null),
    [eraseStatus, setEraseStatus] = useState(null),
    [epoch, setEpoch] = useState(0);
  const pending = useRef(0);
  const mounted = useRef(true);
  const pollInFlight = useRef(false);
  const generation = useRef(0);
  const busyRef = useRef(false);
  const identityRef = useRef(null);
  const pollErrorShown = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);
  const run = useCallback(async (fn, message) => {
    pending.current++;
    generation.current += 1;
    busyRef.current = true;
    setBusy(true);
    setNotice(null);
    try {
      await fn();
      if (message) setNotice({ message, error: false });
    } catch (error) {
      setNotice({ message: error.message, error: true });
    } finally {
      pending.current--;
      busyRef.current = pending.current > 0;
      setBusy(busyRef.current);
    }
  }, []);
  useEffect(() => {
    identityRef.current = identity;
  }, [identity]);
  useEffect(() => {
    run(async () => {
      const [catalog, devices, connection, erase] = await Promise.all([
        api("catalog"),
        api("devices"),
        api("connection"),
        api("screen_erase"),
      ]);
      setCatalog(catalog);
      setDevices(devices);
      identityRef.current = connection;
      setIdentity(connection);
      setEraseStatus(erase);
    });
  }, []);
  const poll = useCallback(async () => {
    if (!mounted.current || busyRef.current || pollInFlight.current) return;
    pollInFlight.current = true;
    const pollGeneration = generation.current;
    try {
      const [nextDevices, nextIdentity, nextErase] = await Promise.all([
        api("devices"),
        api("connection"),
        api("screen_erase"),
      ]);
      if (!mounted.current || pollGeneration !== generation.current) return;
      const previous = identityRef.current;
      pollErrorShown.current = false;
      setDevices(nextDevices);
      identityRef.current = nextIdentity;
      setIdentity(nextIdentity);
      setEraseStatus(nextErase);
      if (previous && !nextIdentity) {
        setNotice({ message: "Keyboard connection lost.", error: true });
      }
      if (path && !nextDevices.some((device) => device.path === path)) {
        setPath("");
      }
      if (
        Boolean(previous) !== Boolean(nextIdentity) ||
        previous?.session !== nextIdentity?.session ||
        previous?.path !== nextIdentity?.path
      )
        setEpoch((value) => value + 1);
    } catch (error) {
      if (
        mounted.current &&
        pollGeneration === generation.current &&
        !pollErrorShown.current
      ) {
        pollErrorShown.current = true;
        setNotice({
          message: `Connection status unavailable: ${error.message}`,
          error: true,
        });
      }
    } finally {
      pollInFlight.current = false;
    }
  }, [path]);
  useEffect(() => {
    const timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [poll]);
  const refresh = () => {
    generation.current += 1;
    run(async () => {
      const [nextDevices, nextIdentity, nextErase] = await Promise.all([
        api("devices"),
        api("connection"),
        api("screen_erase"),
      ]);
      if (!mounted.current) return;
      setDevices(nextDevices);
      identityRef.current = nextIdentity;
      setIdentity(nextIdentity);
      setEraseStatus(nextErase);
      if (path && !nextDevices.some((device) => device.path === path))
        setPath("");
      setEpoch((e) => e + 1);
    });
  };
  const selected = pages.find((page) => page[0] === tab),
    Page = selected[2];
  const blocked = Boolean(eraseStatus?.blocked);
  const deviceConnected = Boolean(identity);
  const connected = deviceConnected && !blocked;
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <strong>EPOMAKER</strong>
          <span>Linux driver</span>
        </div>
        <nav aria-label="Controls">
          {pages.map(([name, Icon]) => (
            <button
              key={name}
              className={tab === name ? "active" : ""}
              disabled={busy}
              aria-current={tab === name ? "page" : undefined}
              onClick={() => {
                setTab(name);
                setNotice(null);
              }}
            >
              <Icon size={25} />
              <span>{name}</span>
            </button>
          ))}
        </nav>
        <div className="device-card">
          <strong>{identity?.model || "Epomaker Glyph"}</strong>
          <span>{deviceConnected ? "Connected" : "Offline preview"}</span>
          <ConnectionTelemetry identity={identity} />
          <Button disabled={busy} onClick={refresh}>
            Refresh devices
          </Button>
          {deviceConnected && (
            <Button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  generation.current += 1;
                  await api("disconnect", {});
                  identityRef.current = null;
                  setIdentity(null);
                  setEpoch((e) => e + 1);
                }, "Disconnected.")
              }
            >
              Disconnect
            </Button>
          )}
        </div>
        <footer>Independent Linux driver</footer>
      </aside>
      <main>
        <header>
          <div>
            <h1>{tab}</h1>
            <p>{selected[3]}</p>
          </div>
          <div className="connection-controls">
            <Select
              aria-label="Device"
              value={path}
              disabled={busy}
              options={[
                ["", "No device selected"],
                ...devices.map((d) => [
                  d.path,
                  `${d.name} · ${d.command_transport}`,
                ]),
              ]}
              onChange={(e) => {
                generation.current += 1;
                setPath(e.target.value);
              }}
            />
            <Button
              primary
              disabled={busy || blocked || !path}
              onClick={() =>
                run(async () => {
                  generation.current += 1;
                  const nextIdentity = await api("connect", { path });
                  identityRef.current = nextIdentity;
                  setIdentity(nextIdentity);
                  setEpoch((e) => e + 1);
                }, "Keyboard connected.")
              }
            >
              Connect
            </Button>
          </div>
        </header>
        {notice && (
          <div
            className={`notice ${notice.error ? "error" : ""}`}
            role={notice.error ? "alert" : "status"}
          >
            {notice.message}
          </div>
        )}
        {eraseStatus?.state === "running" && (
          <div className="notice" role="status">
            Clearing keyboard screen…{" "}
            {Math.floor(eraseStatus.elapsed_seconds || 0)} s elapsed.
          </div>
        )}
        {eraseStatus?.state === "completed" && (
          <div className="notice" role="status">
            Keyboard reported screen clear complete; inspect display.
          </div>
        )}
        {eraseStatus?.state === "uncertain" && (
          <div className="notice error" role="alert">
            Screen erase outcome is unknown:{" "}
            {eraseStatus.error || "inspect the keyboard and acknowledge it."}
          </div>
        )}
        {eraseStatus?.state === "unavailable" && (
          <div className="notice error" role="alert">
            Screen erase status is unavailable. Device controls remain locked
            while the driver checks the operation.
          </div>
        )}
        {busy && (
          <div className="busy-indicator" role="status">
            <LoaderCircle size={18} className="spin" />
            Working…
          </div>
        )}
        {catalog ? (
          <Page
            key={tab}
            catalog={catalog}
            connected={connected}
            identity={identity}
            transport={identity?.transport}
            lightSync={identity?.light_sync}
            screenRatio={screenRatio}
            onScreenRatioChange={setScreenRatio}
            busy={busy}
            eraseStatus={eraseStatus}
            onEraseStatus={async (value) => {
              if (value) {
                setEraseStatus(value);
                return;
              }
              // A lost start response may follow a successfully started erase.
              setEraseStatus({ state: "unavailable", blocked: true });
              setEraseStatus(await api("screen_erase"));
            }}
            onEraseAcknowledged={(value) => {
              setEraseStatus(value);
              setIdentity(null);
              identityRef.current = null;
              setEpoch((e) => e + 1);
            }}
            run={run}
            epoch={epoch}
            onConnectionLost={() => {
              generation.current += 1;
              identityRef.current = null;
              setIdentity(null);
              setEpoch((e) => e + 1);
            }}
          />
        ) : (
          !notice && <p className="muted">Loading device catalog…</p>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
