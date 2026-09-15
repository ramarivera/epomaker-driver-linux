import React from "react";

function validAge(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function validBattery(value) {
  return Number.isInteger(value) && value >= 0 && value <= 100;
}

export default function ConnectionTelemetry({ identity }) {
  if (!identity || identity.transport !== "bluetooth") return null;

  const telemetry = identity.telemetry || {};
  const batteryReported =
    validBattery(telemetry.battery_raw) &&
    validAge(telemetry.battery_age_seconds);
  const statusReported =
    typeof telemetry.online === "boolean" &&
    validAge(telemetry.online_age_seconds);

  return (
    <div className="connection-telemetry" aria-label="Device telemetry">
      <span>
        {batteryReported
          ? `Last battery report: ${telemetry.battery_raw}% · ${Math.floor(telemetry.battery_age_seconds)} s ago`
          : "Battery: Not reported"}
      </span>
      <span>
        {statusReported
          ? `Last device status: ${telemetry.online ? "Online" : "Offline"} · ${Math.floor(telemetry.online_age_seconds)} s ago`
          : "Device status: Not reported"}
      </span>
    </div>
  );
}
