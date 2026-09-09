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
import MacrosEditor from "./macros-editor";
import Display from "./display";
import Settings from "./settings";
import Backups from "./backups";
import "./style.css";
const pages = [
  [
    "Keymap",
    Keyboard,
    Keymap,
    "Select a key to change its assignment.",
    "keymap",
  ],
  [
    "Lighting",
    Lightbulb,
    Lighting,
    "Set effects and paint custom colors.",
    "lighting",
  ],
  [
    "Macros",
    Play,
    MacrosEditor,
    "Create and assign keyboard and mouse sequences.",
    "macros",
  ],
  [
    "Display",
    Monitor,
    Display,
    "Choose images and information for your keyboard.",
    "display",
  ],
  [
    "Settings",
    SettingsIcon,
    Settings,
    "Read and update keyboard preferences.",
    "settings",
  ],
  [
    "Backups",
    Database,
    Backups,
    "Save your configuration and restore it with a recovery copy.",
    "backups",
  ],
];
const GLYPH_UI = {
  profiles: 3,
  fn_modes: [
    { label: "Fn Windows", os_mode: 0 },
    { label: "Fn Mac", os_mode: 1 },
  ],
  submodes: 1,
  matrix_slots: 128,
  macro_slots: 256,
  controls: pages.map((page) => page[4]),
};
function App() {
  const [tab, setTab] = useState("Keymap"),
    [catalog, setCatalog] = useState(null),
    [devices, setDevices] = useState([]),
    [path, setPath] = useState(""),
    [identity, setIdentity] = useState(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(null),
    [epoch, setEpoch] = useState(0);
  const pending = useRef(0);
  const run = useCallback(async (fn, message) => {
    pending.current++;
    setBusy(true);
    setNotice(null);
    try {
      await fn();
      if (message) setNotice({ message, error: false });
    } catch (error) {
      setNotice({ message: error.message, error: true });
    } finally {
      pending.current--;
      setBusy(pending.current > 0);
    }
  }, []);
  useEffect(() => {
    run(async () => {
      const [devices, connection] = await Promise.all([
        api("devices"),
        api("connection"),
      ]);
      const nextCatalog = await api("catalog");
      setDevices(devices);
      setIdentity(connection);
      setCatalog(nextCatalog);
    });
  }, []);
  const refresh = () =>
    run(async () => {
      setDevices(await api("devices"));
      setEpoch((e) => e + 1);
    });
  const ui = identity?.ui || catalog?.ui || GLYPH_UI;
  const visiblePages = pages.filter(
    (page) => !ui.controls || ui.controls.includes(page[4]),
  );
  const selected =
      visiblePages.find((page) => page[0] === tab) || visiblePages[0],
    Page = selected[2];
  useEffect(() => {
    if (!visiblePages.some((page) => page[0] === tab))
      setTab(visiblePages[0][0]);
  }, [identity?.device_id, catalog, tab]);
  const connected = Boolean(identity);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <strong>EPOMAKER</strong>
          <span>Linux driver</span>
        </div>
        <nav aria-label="Controls">
          {visiblePages.map(([name, Icon]) => (
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
          <span>{connected ? "Connected" : "Offline preview"}</span>
          <Button disabled={busy} onClick={refresh}>
            Refresh devices
          </Button>
          {connected && (
            <Button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await api("disconnect", {});
                  const nextCatalog = await api("catalog");
                  setIdentity(null);
                  setCatalog(nextCatalog);
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
              onChange={(e) => setPath(e.target.value)}
            />
            <Button
              primary
              disabled={busy || !path}
              onClick={() =>
                run(async () => {
                  const nextIdentity = await api("connect", { path });
                  const nextCatalog = await api("catalog");
                  setIdentity(nextIdentity);
                  setCatalog(nextCatalog);
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
            ui={ui}
            identity={identity}
            connected={connected}
            busy={busy}
            run={run}
            epoch={epoch}
          />
        ) : (
          !notice && <p className="muted">Loading device catalog…</p>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
